#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CBZ/CBR/CB7 ⇄ EPUB 2.0 双向转换工具 (兼容 Sigil)
输入 .cbz/.cbr/.cb7 → 生成 .epub
输入 .epub          → 生成 .cbz
特性:
- EPUB: 封面 cover.xhtml + cover.xxx, 内页 page_0001.xhtml + image_0001.xxx
- 自定义 CSS（含 @page、div.page-container、img.page-img）
- CBZ: 封面保持原名，其余图片按页面顺序重命名为 image_0001.xxx 起始
- EPUB 与 CBZ 均采用最大兼容压缩 (ZIP_DEFLATED, compresslevel=9)，EPUB 的 mimetype 除外
- OPF 与 NCX 采用字符串模板生成，确保 100% 完美 Sigil 风格缩进
- 支持拖放批量转换
依赖: pip install rarfile py7zr Pillow
"""
import os
import sys
import zipfile
import shutil
import tempfile
import re
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

# ---------- 依赖检查 ----------
def check_dependencies():
    missing = []
    for lib, name in [('rarfile', 'rarfile'), ('py7zr', 'py7zr'), ('PIL', 'Pillow')]:
        try:
            __import__(lib)
        except ImportError:
            missing.append(name)
    if missing:
        print(f"缺少依赖，请执行：pip install {' '.join(missing)}")
        sys.exit(1)

check_dependencies()

import rarfile
import py7zr
from PIL import Image

# ---------- 常量 ----------
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}
ALLOWED_IMG = {'.jpg', '.jpeg', '.png', '.gif'}   # EPUB 2.0 推荐格式

# ---------- 工具函数 ----------
def natural_sort_key(s):
    """字符串自然排序键：将数字部分转为整数"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

def get_images(directory):
    """递归获取所有图片，自然排序"""
    imgs = []
    for root, _, files in os.walk(directory):
        for f in files:
            if Path(f).suffix.lower() in IMAGE_EXTS:
                imgs.append(os.path.join(root, f))
    imgs.sort(key=lambda p: natural_sort_key(os.path.basename(p)))
    return imgs

def find_cover(images):
    """从图片列表中找出封面（文件名含 cover），否则返回第一张"""
    for i, p in enumerate(images):
        if 'cover' in os.path.splitext(os.path.basename(p))[0].lower():
            return p, i
    return (images[0], 0) if images else (None, None)

def process_img(src, dest_dir, base_name):
    """复制/转换图片到目标目录，重命名为 base_name.扩展名，返回 (文件名, epub相对路径)"""
    ext = Path(src).suffix.lower()
    if ext in ALLOWED_IMG:
        dest_name = f"{base_name}{ext}"
        shutil.copy2(src, os.path.join(dest_dir, dest_name))
    else:
        img = Image.open(src)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        dest_name = f"{base_name}.png"
        img.save(os.path.join(dest_dir, dest_name), "PNG")
    return dest_name, f"Images/{dest_name}"

# ---------- EPUB 生成 ----------
def generate_epub(archive):
    """将 CBZ/CBR/CB7 转换为 EPUB 2.0"""
    in_path = Path(archive)
    if not in_path.exists():
        print(f"文件不存在: {archive}")
        return

    # 询问是否为日漫
    manga_input = input(f"【{in_path.name}】是否为日漫（从右向左翻页）？(y/回车=是, n=否): ").strip().lower()
    is_rtl = manga_input in ('y', 'yes', '')

    title = in_path.stem
    out_epub = in_path.with_suffix('.epub')
    ext = in_path.suffix.lower()
    
    with tempfile.TemporaryDirectory() as tmp:
        extract_dir = os.path.join(tmp, "extracted")
        os.makedirs(extract_dir)
        epub_root = os.path.join(tmp, "epub")
        os.makedirs(epub_root)
        
        # 解压
        try:
            if ext == '.cbz':
                with zipfile.ZipFile(archive) as z:
                    z.extractall(extract_dir)
            elif ext == '.cbr':
                with rarfile.RarFile(archive) as r:
                    r.extractall(extract_dir)
            elif ext == '.cb7':
                with py7zr.SevenZipFile(archive) as s:
                    s.extractall(extract_dir)
            else:
                print(f"不支持格式: {ext}")
                return
        except Exception as e:
            print(f"解压失败: {e}")
            return
            
        images = get_images(extract_dir)
        if not images:
            print("未找到图片")
            return
            
        cover_img, cover_idx = find_cover(images)
        
        # 创建 EPUB 目录结构
        oebps = os.path.join(epub_root, "OEBPS")
        img_dir = os.path.join(oebps, "Images")
        txt_dir = os.path.join(oebps, "Text")
        css_dir = os.path.join(oebps, "Styles")
        meta_dir = os.path.join(epub_root, "META-INF")
        for d in (img_dir, txt_dir, css_dir, meta_dir):
            os.makedirs(d, exist_ok=True)
            
        # 用户自定义 CSS
        css = """@page {
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
}"""
        with open(os.path.join(css_dir, "styles.css"), "w", encoding="utf-8") as f:
            f.write(css)
            
        # 处理页面
        pages = []
        counter = 1
        for idx, img_path in enumerate(images):
            is_cover = (idx == cover_idx)
            if is_cover:
                xhtml_base = "cover"
                img_base = "cover"
                nav_label = "Cover"
            else:
                xhtml_base = f"page_{counter:04d}"
                img_base = f"image_{counter:04d}"
                nav_label = str(counter)
                counter += 1
                
            page_id = xhtml_base
            img_id = f"img-{img_base}"
            img_fname, img_epub = process_img(img_path, img_dir, img_base)
            
            # 生成 XHTML
            xhtml_name = f"{xhtml_base}.xhtml"
            xhtml_path = os.path.join(txt_dir, xhtml_name)
            xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">

<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{nav_label}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/styles.css"/>
</head>

<body>
  <div class="page-container"><img class="page-img" src="../{img_epub}" alt="{nav_label}"/></div>
</body>
</html>'''
            with open(xhtml_path, "w", encoding="utf-8") as f:
                f.write(xhtml)
            pages.append((page_id, img_id, xhtml_name, nav_label, img_fname, img_epub, is_cover))
            
        # ========== OPF 生成 (改用字符串模板，确保完美 Sigil 风格缩进) ==========
        book_id = f"urn:uuid:{uuid.uuid4()}"
        
        # 1. 准备 cover meta
        cover_meta = ""
        for pg in pages:
            if pg[6]:  # is_cover
                cover_meta = f'    <meta name="cover" content="{pg[1]}"/>'
                break
                
        # 2. 组装 metadata
        metadata_content = f'''  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title}</dc:title>
    <dc:creator opf:role="aut">Unknown</dc:creator>
    <dc:language>zh-TW</dc:language>
    <dc:identifier opf:scheme="UUID" id="BookId">{book_id}</dc:identifier>'''
        if cover_meta:
            metadata_content += f'\n{cover_meta}'
        metadata_content += '\n  </metadata>'
        
        # 3. 组装 manifest
        manifest_items = '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
        manifest_items += '    <item id="css" href="Styles/styles.css" media-type="text/css"/>\n'
        for pid, imgid, _, _, fname, epub_path, _ in pages:
            ext_img = Path(fname).suffix.lower()
            mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}.get(ext_img, 'image/jpeg')
            manifest_items += f'    <item id="{imgid}" href="{epub_path}" media-type="{mime}"/>\n'
        for pid, _, xname, _, _, _, _ in pages:
            manifest_items += f'    <item id="{pid}" href="Text/{xname}" media-type="application/xhtml+xml"/>\n'
            
        # 4. 组装 spine
        spine_attrs = 'toc="ncx"'
        if is_rtl:
            spine_attrs += ' page-progression-direction="rtl"'
            
        spine_items = ""
        for pid, _, _, _, _, _, _ in pages:
            spine_items += f'    <itemref idref="{pid}"/>\n'
            
        # 5. 拼接完整 OPF
        opf_content = f'''<?xml version="1.0" encoding="utf-8"?>
<package version="2.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
{metadata_content}
  <manifest>
{manifest_items}  </manifest>
  <spine {spine_attrs}>
{spine_items}  </spine>
</package>'''
        
        with open(os.path.join(oebps, 'content.opf'), "w", encoding="utf-8") as f:
            f.write(opf_content)
        # ======================================================================
        
        # ========== NCX 生成 (字符串模板，杜绝多余空行) ==========
        nav_points = ""
        for i, (pid, _, xname, label, _, _, _) in enumerate(pages, 1):
            nav_points += f'''    <navPoint id="{pid}" playOrder="{i}">
      <navLabel>
        <text>{label}</text>
      </navLabel>
      <content src="Text/{xname}"/>
    </navPoint>
'''
        ncx_content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
   "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{title}</text>
  </docTitle>
  <navMap>
{nav_points}  </navMap>
</ncx>'''
        with open(os.path.join(oebps, 'toc.ncx'), "w", encoding="utf-8") as f:
            f.write(ncx_content)
        # =========================================================
            
        # container.xml
        with open(os.path.join(meta_dir, 'container.xml'), 'w', encoding='utf-8') as f:
            f.write('''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>''')
            
        # mimetype
        with open(os.path.join(epub_root, 'mimetype'), 'w', encoding='utf-8') as f:
            f.write('application/epub+zip')
            
        # 打包 EPUB（mimetype 不压缩，其余最大压缩）
        with zipfile.ZipFile(out_epub, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            zout.write(os.path.join(epub_root, 'mimetype'), 'mimetype', compress_type=zipfile.ZIP_STORED)
            for root, _, files in os.walk(epub_root):
                for file in files:
                    full = os.path.join(root, file)
                    arc = os.path.relpath(full, epub_root)
                    if arc == 'mimetype':
                        continue
                    zout.write(full, arc, compress_type=zipfile.ZIP_DEFLATED)
                    
        print(f"✓ 已生成 EPUB: {out_epub}")

# ---------- CBZ 生成 ----------
def epub_to_cbz(epub_path):
    """从 EPUB 提取图片，按页面顺序重命名，封面保留原名，其余 image_0001.xxx 起始，CBZ 使用最大 deflate 压缩"""
    in_path = Path(epub_path)
    if not in_path.exists():
        print(f"文件不存在: {epub_path}")
        return
    out_cbz = in_path.with_suffix('.cbz')
    with tempfile.TemporaryDirectory() as tmp:
        # 解压 EPUB
        with zipfile.ZipFile(epub_path, 'r') as z:
            z.extractall(tmp)
            
        # 定位 container.xml
        container_path = os.path.join(tmp, 'META-INF', 'container.xml')
        if not os.path.exists(container_path):
            print("不是有效的 EPUB (缺少 container.xml)")
            return
            
        tree = ET.parse(container_path)
        root = tree.getroot()
        ns_cnt = {'container': 'urn:oasis:names:tc:opendocument:xmlns:container'}
        rootfile = root.find('.//container:rootfile', ns_cnt)
        if rootfile is None:
            print("container.xml 中未找到 rootfile")
            return
            
        opf_rel = rootfile.get('full-path')
        opf_full = os.path.join(tmp, opf_rel)
        if not os.path.exists(opf_full):
            print(f"OPF 文件缺失: {opf_rel}")
            return
            
        opf_dir = os.path.dirname(opf_rel)
        opf_tree = ET.parse(opf_full)
        opf_root = opf_tree.getroot()
        ns_opf = 'http://www.idpf.org/2007/opf'
        
        # manifest 信息
        manifest = {}
        manifest_elem = opf_root.find(f'{{{ns_opf}}}manifest')
        if manifest_elem is None:
            print("OPF 缺少 manifest")
            return
        for item in manifest_elem.findall(f'{{{ns_opf}}}item'):
            mid = item.get('id')
            href = item.get('href')
            mtype = item.get('media-type')
            manifest[mid] = {'href': href, 'media-type': mtype}
            
        # 确定封面图片
        cover_img_href = None
        metadata = opf_root.find(f'{{{ns_opf}}}metadata')
        if metadata is not None:
            for meta_elem in metadata.findall(f'{{{ns_opf}}}meta'):
                if meta_elem.get('name') == 'cover':
                    cover_id = meta_elem.get('content')
                    if cover_id in manifest:
                        cover_img_href = manifest[cover_id]['href']
                    break
                    
        # 按 spine 顺序获取页面
        spine = opf_root.find(f'{{{ns_opf}}}spine')
        if spine is None:
            print("OPF 缺少 spine")
            return
            
        ordered_images = []
        for itemref in spine.findall(f'{{{ns_opf}}}itemref'):
            idref = itemref.get('idref')
            if idref not in manifest:
                continue
            page_info = manifest[idref]
            if not page_info['media-type'].startswith('application/xhtml+xml'):
                continue
            page_href = page_info['href']
            xhtml_abs = os.path.normpath(os.path.join(tmp, opf_dir, page_href))
            if not os.path.exists(xhtml_abs):
                continue
            try:
                xhtml_tree = ET.parse(xhtml_abs)
                xhtml_root = xhtml_tree.getroot()
                img_elem = None
                for elem in xhtml_root.iter():
                    if elem.tag.endswith('}img') or elem.tag == 'img':
                        img_elem = elem
                        break
                if img_elem is not None:
                    src = img_elem.get('src')
                    if src:
                        xhtml_dir = os.path.dirname(xhtml_abs)
                        img_abs = os.path.normpath(os.path.join(xhtml_dir, src))
                        if os.path.exists(img_abs):
                            img_href = os.path.relpath(img_abs, os.path.join(tmp, opf_dir))
                            ordered_images.append((img_abs, img_href))
            except Exception:
                continue
                
        if not ordered_images:
            print("未能通过 spine 提取图片顺序，将使用 manifest 排序")
            for mid, info in manifest.items():
                if info['media-type'].startswith('image/'):
                    img_abs = os.path.normpath(os.path.join(tmp, opf_dir, info['href']))
                    if os.path.exists(img_abs):
                        ordered_images.append((img_abs, info['href']))
            ordered_images.sort(key=lambda x: natural_sort_key(x[1]))
            
        # 分离封面与其他图片
        cover_img = None
        other_imgs = []
        for img_abs, img_href in ordered_images:
            if cover_img_href and img_href == cover_img_href:
                cover_img = (img_abs, img_href)
            else:
                other_imgs.append((img_abs, img_href))
                
        if not cover_img and other_imgs:
            for i, (img_abs, img_href) in enumerate(other_imgs):
                if 'cover' in os.path.basename(img_href).lower():
                    cover_img = (img_abs, img_href)
                    del other_imgs[i]
                    break
                    
        final_images = []
        if cover_img:
            final_images.append(cover_img)
        final_images.extend(other_imgs)
        
        if not final_images:
            print("EPUB 中未找到图片")
            return
            
        # 重命名并复制到输出目录
        img_out_dir = os.path.join(tmp, 'cbz_out')
        os.makedirs(img_out_dir, exist_ok=True)
        counter = 1
        for idx, (img_abs, img_href) in enumerate(final_images):
            if idx == 0 and cover_img is not None:
                dest_name = os.path.basename(img_href)
            else:
                ext = os.path.splitext(img_href)[1]
                dest_name = f"image_{counter:04d}{ext}"
                counter += 1
            shutil.copy2(img_abs, os.path.join(img_out_dir, dest_name))
            
        # 打包为 CBZ
        with zipfile.ZipFile(out_cbz, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for fname in sorted(os.listdir(img_out_dir)):
                zout.write(os.path.join(img_out_dir, fname), fname)
                
        print(f"✓ 已生成 CBZ: {out_cbz}")

# ---------- 入口 ----------
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("拖放文件到脚本，或命令行使用：")
        print("  .cbz/.cbr/.cb7 → 生成 .epub")
        print("  .epub           → 生成 .cbz")
        sys.exit(0)
        
    for f in sys.argv[1:]:
        ext = Path(f).suffix.lower()
        if ext == '.epub':
            epub_to_cbz(f)
        elif ext in ('.cbz', '.cbr', '.cb7'):
            generate_epub(f)
        else:
            print(f"不支持的文件类型: {f}")