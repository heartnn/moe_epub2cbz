#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EPUB 格式标准化修复工具
功能：
1. 统一 container.xml 和 styles.css 为 2 空格缩进（直接替换为标准版）
2. 清除 content.opf 中错误的 opf: 前缀，重建为 Sigil 标准格式（2空格缩进）
3. 清除 toc.ncx 中的多余空行，重建为标准格式（2空格缩进）
4. 批量处理时只询问一次 RTL 状态，已符合目标的文件不会重复修改该属性
用法：拖放一个或多个 .epub 文件到脚本上
"""
import os
import sys
import zipfile
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET

# ---------- 常量与标准模板 ----------
OPF_NS = 'http://www.idpf.org/2007/opf'
DC_NS = 'http://purl.org/dc/elements/1.1/'
NCX_NS = 'http://www.daisy.org/z3986/2005/ncx/'

STANDARD_CONTAINER = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''

STANDARD_CSS = '''@page {
  margin: 0;
}
body {
  margin: 0;
  padding: 0;
  text-align: center;
}
div.page-container {
  margin: 0;
  padding: 0;
  text-align: center;
}
img.page-img {
  max-width: 100%;
  height: auto;
}'''


def check_epub_rtl_status(epub_path):
    """快速检查单个 EPUB 是否已包含 rtl 属性"""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(epub_path, 'r') as z:
                # 找 container.xml
                container_data = z.read('META-INF/container.xml').decode('utf-8')
                c_root = ET.fromstring(container_data)
                rootfile = c_root.find('.//{*}rootfile')
                if rootfile is None:
                    return False
                opf_rel = rootfile.get('full-path')
                
                # 读 opf
                opf_data = z.read(opf_rel).decode('utf-8')
                o_root = ET.fromstring(opf_data)
                spine = o_root.find(f'.//{{{OPF_NS}}}spine')
                if spine is not None and spine.get('page-progression-direction') == 'rtl':
                    return True
        return False
    except Exception:
        return False


def fix_single_epub(epub_path, target_rtl):
    """修复单个 EPUB 文件的格式"""
    in_path = Path(epub_path)
    print(f"正在处理: {in_path.name} ...", end=" ")
    
    with tempfile.TemporaryDirectory() as tmp:
        # 1. 解压
        with zipfile.ZipFile(epub_path, 'r') as z:
            z.extractall(tmp)
            
        # 2. 定位 OPF 路径
        container_path = os.path.join(tmp, 'META-INF', 'container.xml')
        if not os.path.exists(container_path):
            print("✗ 缺少 container.xml")
            return
            
        c_tree = ET.parse(container_path)
        rootfile = c_tree.getroot().find('.//{*}rootfile')
        if rootfile is None:
            print("✗ 未找到 rootfile")
            return
        opf_rel = rootfile.get('full-path')
        opf_abs = os.path.join(tmp, opf_rel)
        opf_dir = os.path.dirname(opf_rel)
        
        if not os.path.exists(opf_abs):
            print("✗ OPF 文件缺失")
            return

        # 3. 替换 container.xml 和 styles.css (直接覆盖为标准 2 空格版)
        with open(container_path, 'w', encoding='utf-8') as f:
            f.write(STANDARD_CONTAINER)
            
        css_path = os.path.join(tmp, opf_dir, 'Styles', 'styles.css')
        if os.path.exists(css_path):
            with open(css_path, 'w', encoding='utf-8') as f:
                f.write(STANDARD_CSS)

        # 4. 解析并重建 content.opf
        o_tree = ET.parse(opf_abs)
        o_root = o_tree.getroot()
        
        # 提取元数据
        unique_id = o_root.get('unique-identifier', 'BookId')
        meta = o_root.find(f'.//{{{OPF_NS}}}metadata')
        
        def get_dc_text(tag):
            elem = meta.find(f'{{{DC_NS}}}{tag}') if meta is not None else None
            return elem.text if elem is not None and elem.text else 'Unknown'
            
        title = get_dc_text('title')
        language = get_dc_text('language')
        creator = get_dc_text('creator')
        
        # 找 identifier
        book_id = 'urn:uuid:unknown'
        if meta is not None:
            id_elem = meta.find(f'{{{DC_NS}}}identifier')
            if id_elem is not None:
                book_id = id_elem.text or book_id
                
        # 找 cover meta
        cover_meta = ""
        if meta is not None:
            for m in meta.findall(f'{{{OPF_NS}}}meta'):
                if m.get('name') == 'cover':
                    cover_meta = f'    <meta name="cover" content="{m.get("content")}"/>\n'
                    break

        # 提取 manifest
        manifest_items = []
        manifest_elem = o_root.find(f'.//{{{OPF_NS}}}manifest')
        if manifest_elem is not None:
            for item in manifest_elem.findall(f'{{{OPF_NS}}}item'):
                manifest_items.append({
                    'id': item.get('id'),
                    'href': item.get('href'),
                    'media-type': item.get('media-type')
                })
                
        # 提取 spine 并决定最终 rtl 状态
        spine = o_root.find(f'.//{{{OPF_NS}}}spine')
        current_is_rtl = (spine is not None and spine.get('page-progression-direction') == 'rtl')
        
        # 逻辑：如果 target_rtl 是 None，表示保持原样；否则使用 target_rtl
        final_is_rtl = current_is_rtl if target_rtl is None else target_rtl
        
        spine_items = []
        if spine is not None:
            for itemref in spine.findall(f'{{{OPF_NS}}}itemref'):
                spine_items.append(itemref.get('idref'))
                
        # 重建 OPF 字符串 (2空格缩进，无前缀)
        metadata_content = f'''  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title}</dc:title>
    <dc:creator opf:role="aut">{creator}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:identifier opf:scheme="UUID" id="BookId">{book_id}</dc:identifier>'''
        if cover_meta:
            metadata_content += f'\n{cover_meta}'
        metadata_content += '  </metadata>'
        
        manifest_str = "    <item id=\"ncx\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\"/>\n"
        for item in manifest_items:
            # 跳过 ncx，因为上面已经硬编码了，避免重复（或者保留原样也行，这里我们重建以确保顺序整洁）
            if item['id'] == 'ncx':
                continue
            manifest_str += f"    <item id=\"{item['id']}\" href=\"{item['href']}\" media-type=\"{item['media-type']}\"/>\n"
            
        spine_attrs = 'toc="ncx"'
        if final_is_rtl:
            spine_attrs += ' page-progression-direction="rtl"'
            
        spine_str = ""
        for idref in spine_items:
            spine_str += f"    <itemref idref=\"{idref}\"/>\n"
            
        opf_content = f'''<?xml version="1.0" encoding="utf-8"?>
<package version="2.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
{metadata_content}
  <manifest>
{manifest_str}  </manifest>
  <spine {spine_attrs}>
{spine_str}  </spine>
</package>'''
        
        with open(opf_abs, 'w', encoding='utf-8') as f:
            f.write(opf_content)

        # 5. 解析并重建 toc.ncx (消除多余空行)
        ncx_path = os.path.join(tmp, opf_dir, 'toc.ncx')
        if os.path.exists(ncx_path):
            n_tree = ET.parse(ncx_path)
            n_root = n_tree.getroot()
            
            uid = 'unknown'
            head = n_root.find(f'{{{NCX_NS}}}head')
            if head is not None:
                uid_meta = head.find(f"{{{NCX_NS}}}meta[@name='dtb:uid']")
                if uid_meta is not None:
                    uid = uid_meta.get('content', uid)
                    
            doc_title = title
            doc_title_elem = n_root.find(f'{{{NCX_NS}}}docTitle/{{{NCX_NS}}}text')
            if doc_title_elem is not None and doc_title_elem.text:
                doc_title = doc_title_elem.text
                
            nav_points = ""
            nav_map = n_root.find(f'{{{NCX_NS}}}navMap')
            if nav_map is not None:
                for i, np in enumerate(nav_map.findall(f'{{{NCX_NS}}}navPoint'), 1):
                    pid = np.get('id', f'nav_{i}')
                    play_order = np.get('playOrder', str(i))
                    
                    label = 'Unknown'
                    nl = np.find(f'{{{NCX_NS}}}navLabel/{{{NCX_NS}}}text')
                    if nl is not None and nl.text:
                        label = nl.text
                        
                    src = ''
                    content = np.find(f'{{{NCX_NS}}}content')
                    if content is not None:
                        src = content.get('src', '')
                        
                    nav_points += f'''    <navPoint id="{pid}" playOrder="{play_order}">
      <navLabel>
        <text>{label}</text>
      </navLabel>
      <content src="{src}"/>
    </navPoint>
'''
            ncx_content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
   "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{uid}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{doc_title}</text>
  </docTitle>
  <navMap>
{nav_points}  </navMap>
</ncx>'''
            with open(ncx_path, 'w', encoding='utf-8') as f:
                f.write(ncx_content)

        # 6. 重新打包 EPUB
        with zipfile.ZipFile(epub_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            mimetype_path = os.path.join(tmp, 'mimetype')
            if os.path.exists(mimetype_path):
                zout.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)
            for dirpath, _, filenames in os.walk(tmp):
                for fname in filenames:
                    full = os.path.join(dirpath, fname)
                    arc = os.path.relpath(full, tmp)
                    if arc == 'mimetype':
                        continue
                    zout.write(full, arc, compress_type=zipfile.ZIP_DEFLATED)
                    
        print("✓ 完成")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("拖放 .epub 文件到脚本，或命令行使用：")
        print("  python fix_epub_format.py 文件1.epub 文件2.epub ...")
        sys.exit(0)
        
    epub_files = [f for f in sys.argv[1:] if Path(f).suffix.lower() == '.epub']
    if not epub_files:
        print("未找到有效的 .epub 文件")
        sys.exit(0)
        
    print(f"共检测到 {len(epub_files)} 个 EPUB 文件。正在扫描 RTL 状态...")
    
    # 预扫描 RTL 状态
    rtl_counts = {'yes': 0, 'no': 0}
    for f in epub_files:
        if check_epub_rtl_status(f):
            rtl_counts['yes'] += 1
        else:
            rtl_counts['no'] += 1
            
    print(f"扫描完毕：{rtl_counts['yes']} 个已包含 rtl，{rtl_counts['no']} 个未包含。")
    
    # 智能询问逻辑
    target_rtl = None # None 表示保持每个文件原有的状态
    if rtl_counts['no'] == 0:
        ans = input("所有文件已包含 rtl 属性。是否需要【移除】它们？(y=移除, 回车=保持原样仅修复格式): ").strip().lower()
        if ans in ('y', 'yes'):
            target_rtl = False
    else:
        ans = input(f"是否为这批文件统一【添加】 rtl 属性？(y/回车=添加, n=不添加仅修复格式): ").strip().lower()
        if ans in ('y', 'yes', ''):
            target_rtl = True
        else:
            target_rtl = False # 用户明确选 n，则统一设为 False (移除)
            
    print("\n开始修复格式...")
    for f in epub_files:
        fix_single_epub(f, target_rtl)
        
    print("\n🎉 全部处理完毕！")