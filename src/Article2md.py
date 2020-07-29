# -*- coding: utf-8 -*-
import configparser
import os
import os.path
import re

import html2text
import requests
from lxml import etree
from requests_toolbelt import MultipartEncoder


class Article2md:
    def __init__(self):
        super().__init__()
        self.title = None
        self.file_name = None  # 文件名称.md
        self.file_path = None  # 路径/文件名称.md
        self.url = None  # 链接
        self.article = None  # 内容
        self.md = None  # 总md 字符串
        self.html_file_path = None  # 路径/文件名称.html
        self.language_list = []  # 语言列表

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36",
        }
        self.base_path = "files/"
        self.html_path = "html/"
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
        if not os.path.exists(self.html_path):
            os.makedirs(self.html_path)

        # cookie有特殊字符% 会被当成占位符 要用RawConfigParser
        config = configparser.RawConfigParser()
        config.read("config.ini", encoding="utf-8")

        self.save_to_yuque = config.getboolean("setting", "save_to_yuque")
        self.token = config.get("setting", "token")
        self.cookie = config.get("setting", "cookie")
        self.book_id = config.get("setting", "book_id")

    # 追加原链接到头部
    def convert2md(self):
        md_parser = html2text.HTML2Text()
        md_parser.wrap_links = False  # 取消链接换行
        md_parser.single_line_break = True
        md_parser.mark_code = True
        self.md = md_parser.handle(self.article)
        self.md = '<a href="{}" target="_blank" rel="noopener noreferrer">原文链接</a>\n\n'.format(self.url) + self.md

    # 获取语言列表
    def parse_language_list(self):
        # 从页面中取到所有语言
        with open(self.html_file_path, "r", encoding="utf-8") as f:
            html = f.read()
            parser = etree.HTML(html)
            code_list = parser.xpath("//pre/code")
            for code in code_list:
                code_class = code.xpath("./@class")
                lang = code_class[0].replace("language-", "").replace("prism ", "") if code_class else ''
                if lang == 'py':
                    lang = 'python'
                self.language_list.append(lang)
        print(len(self.language_list), self.language_list)

    # 选取语言
    def get_language(self, index):
        lang = self.language_list[index]
        if lang:
            return lang
        else:
            with open(self.html_file_path, "r", encoding="utf-8") as f:
                html = f.read()
                # or '占位' in html
                if '<?xml' in html or '<dependency>' in html:
                    return 'xml'
                elif 'spring:' in html:
                    return 'yaml'
                elif '@Bean' in html or 'public' in html or '@Controller' in html:
                    return 'java'
                else:
                    return ''

    # 格式化md
    def format_md(self):
        new_md = ""  # 总md
        code_md = ""  # 存代码块的md
        index = 0
        with open(self.file_path, "r", encoding="utf-8") as f:
            begin = False
            for row in f.readlines():
                # 为[code] 改成```语言
                if "[code]" in row:
                    code_md += "```#{语言占位符}\n"
                    begin = True
                    continue

                # 为[/code] 改成```
                if "[/code]" in row:
                    code_md += "```\n"
                    # 判断代码块的语言
                    code_language = self.get_language(index)
                    print("取出语言:", code_language)
                    index += 1
                    # 更改代码块md的语言
                    code_md = code_md.replace("#{语言占位符}", code_language)
                    # 追加代码块md
                    new_md += code_md
                    # 清空代码块md
                    code_md = ""
                    begin = False
                    continue

                # 中间内容 减少4个空格
                if begin:
                    code_row = row[4:]
                    if code_row:
                        code_md += code_row
                else:
                    new_md += row.strip() + "\n"

        self.md = new_md
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.md)

        print("格式化md内容...")

    # 清理多余内容
    def clean_article(self):
        # 移除<link>
        self.article = re.sub("<link.*?>", '', self.article)

        # 移除目录
        self.article = re.sub('<div class="toc"[\s\S]*?</p>', '', self.article)

        # 移除svg
        self.article = re.sub('<svg[\s\S]*?</svg>', '', self.article)
        self.article = self.article.replace("<!-- flowchart 箭头图标 勿删 -->", "")

        if 'jianshu' in self.url:
            self.article = re.sub('<div class="image-caption".*?</div>', '', self.article)
            self.article = self.article.replace('data-original-src="', 'src="https:')

    # 转存到语雀
    def import2YuQue(self):
        if not self.save_to_yuque:
            return

        print("开始上传到语雀")

        url = "https://www.yuque.com/api/import?ctoken=" + self.token
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
            "cookie": self.cookie,
            "content-type": "multipart/form-data; boundary=----WebKitFormBoundaryKPjN0GYtWEjAni5F",
        }

        m = MultipartEncoder(
            fields={
                "book_id": self.book_id,
                "type": "markdown",
                "import_type": "create",
                "options": '{"enableLatex":1}',
                'file': (
                    self.file_name, open(self.file_path, 'rb'),
                    'application/octet-stream', {'Expires': '0'})
            },
            boundary="----WebKitFormBoundaryKPjN0GYtWEjAni5F"
        )

        r = requests.post(url, data=m, headers=headers)
        if r.json().get("data"):
            print("上传成功!!!")
        else:
            print("上传失败! 返回结果:", r.text)

    # 去除标题特殊字符
    def fromat_title(self, reg_title, resp_text):
        self.title = re.sub(r"[/\\:*?\"<>|]", "_", re.findall(reg_title, resp_text)[0])

    # 简书入口
    def jianshu(self):
        resp = requests.get(self.url, headers=self.headers)
        self.article = "<article " + re.findall("<article([\\s\\S]*)</article>", resp.text)[0] + "</article>"

        self.fromat_title('<h1 class="_1RuRku">(.*?)</h1>', resp.text)

        # 清理多余标签内容
        self.clean_article()

        # 保存html内容页面
        self.html_file_path = self.html_path + self.title + ".html"
        with open(self.html_file_path, "w", encoding="utf-8") as f:
            f.write(self.article)
        print("页面 {} 保存成功!".format(self.html_file_path))

        # 解析语言列表
        self.parse_language_list()

        # 内容转换为md,同时写入原链接
        self.convert2md()

        # 名称 路径
        self.file_name = self.title + ".md"
        self.file_path = self.base_path + self.file_name

        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.md)
        print("文件 {} 下载成功!".format(self.file_path))

        self.format_md()

    # csdn入口
    def csdn(self):
        resp = requests.get(self.url, headers=self.headers)
        # 标题
        title = re.findall("<h1.*?>(.*?)</h1>", resp.text)[0]
        # 内容
        self.article = "<article " + re.findall("<article([\\s\\S]*)</article>", resp.text)[0] + "</article>"

        # 清理多余标签内容
        self.clean_article()

        # 保存html内容页面
        self.html_file_path = self.html_path + title + ".html"
        with open(self.html_file_path, "w", encoding="utf-8") as f:
            f.write(self.article)
        print("页面 {} 保存成功!".format(self.html_file_path))

        # 解析语言列表
        self.parse_language_list()

        # 内容转换为md,同时写入原链接
        self.convert2md()

        # 名称 路径
        self.file_name = title + ".md"
        self.file_path = self.base_path + self.file_name

        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.md)
        print("文件 {} 下载成功!".format(self.file_path))

        self.format_md()

    # 总入口
    def run(self):
        print("************** Markdown转换器 **************")
        print("版本号: 1.0")
        print("作者: Carve")
        print("公众号: Carve自修室")
        print("支持类型: CSDN，简书")

        print("***************************************")

        while True:
            self.url = input("请输入文章地址:")

            if 'jianshu' in self.url:
                self.jianshu()
            else:
                self.csdn()

            self.import2YuQue()
            print()
