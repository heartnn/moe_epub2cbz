# CBZ/CBR/CB7 ⇄ EPUB 2.0 双向转换工具 (兼容 Sigil)

从乱序的epub生成正常顺序的cbz，或从cbz/cbr/cb7生成epub

输入 .cbz/.cbr/.cb7 → 生成 .epub
输入 .epub          → 生成 .cbz

---

## 特性

  - EPUB: 封面 cover.xhtml + cover.xxx, 内页 page_0001.xhtml + image_0001.xxx
  - 自定义 CSS（含 @page、div.page-container、img.page-img）
  - CBZ: 封面保持原名，其余图片按页面顺序重命名为 image_0001.xxx 起始
  - EPUB 与 CBZ 均采用最大兼容压缩 (ZIP_DEFLATED, compresslevel=9)，EPUB 的 mimetype 除外
  - 支持拖放批量转换

---

## 用法

先安装依赖：

```python
pip install rarfile py7zr Pillow
```

可使用命令行或直接拖放文件到 `epub2cbz.py` (需设定.py的打开方式为Python) 执行，支持批量操作。

---

## Windows下打包成执行文件

需准备 `UnRAR.exe` 放入 `epub2cbz.py` 所在目录(如果需要转换CBR文件)，然后执行：

```
pyinstaller --onefile --name "epub2cbz" --add-binary "UnRAR.exe;." epub2cbz.py
```

在Python 3.13下测试成功。
