"""Render a Markdown doc to PDF with headless Chrome. Usage: md_to_pdf.py in.md out.pdf "Footer text"."""
import os, subprocess, sys, tempfile
import markdown2

src, out, footer = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "")
body = markdown2.markdown(open(src).read(), extras=["tables", "fenced-code-blocks", "header-ids"])
css = """
@page { size: A4; margin: 15mm 14mm 17mm 14mm;
  @bottom-left { content: "%s"; font: 8px sans-serif; color:#5C6670 }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8px sans-serif; color:#5C6670 } }
body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10.2px; line-height: 1.5; color:#1A222B; }
h1 { font-size: 22px; margin: 0 0 8px; }
h2 { font-size: 15.5px; margin: 20px 0 6px; padding-top: 7px; border-top: 2px solid #1A222B; page-break-after: avoid; }
h3 { font-size: 12.5px; margin: 14px 0 4px; color:#B4602A; page-break-after: avoid; }
ul, ol { padding-left: 18px; margin: 4px 0 8px; } li { margin-bottom: 2px; }
table { border-collapse: collapse; width: 100%%; margin: 6px 0 10px; font-size: 9.2px; }
tr { page-break-inside: avoid; }
th { background:#EDEFEA; color:#5C6670; text-align:left; } th, td { border: 0.6px solid #C9CFC6; padding: 4px 6px; vertical-align: top; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9px; background:#ECEEE9; padding: 0 3px; border-radius: 2px; }
pre { background:#ECEEE9; padding: 8px 10px; font-size: 8.6px; line-height: 1.45; white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { margin: 6px 0 10px; padding: 6px 10px; background:#F7ECD2; border-left: 3px solid #8A5A00; } blockquote p { margin: 0; }
hr { border: 0; border-top: 1px solid #C9CFC6; margin: 12px 0; }
""" % footer
html = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False)
html.write(f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>")
html.close()
subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
	f"--print-to-pdf={out}", "file://" + html.name], check=True, capture_output=True)
os.unlink(html.name)
print(out)
