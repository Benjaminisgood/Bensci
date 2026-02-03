"""
解析器通用基类。
位于benfinder 根目录，便于后续拓展其它出版社解析器。
"""

from abc import ABCMeta, abstractclassmethod
from pathlib import Path
from typing import List, Sequence


class BaseParser(metaclass=ABCMeta):
    """
    所有解析器共同遵循的接口定义。

    - suffix/suffixes: 解析器期望的文件后缀。
    - parser: BeautifulSoup 使用的解析器名称。
    - para_tags/table_tags/figure_tags: 用于定位正文段落、表格、图片的标签集合。
    """

    suffix: str = ".xml"
    suffixes: Sequence[str] = ()
    parser: str
    content_type: str = "xml"
    para_tags: List[str]
    table_tags: List[str]
    figure_tags: List[str]

    @classmethod
    def all_tags(cls) -> List[str]:
        """把正文/图/表的标签合并，方便统一遍历。"""
        return cls.para_tags + cls.table_tags + cls.figure_tags

    @classmethod
    def check_suffix(cls, suffix: str) -> bool:
        """快速判断文件是否属于本解析器负责的类型。"""
        candidates = list(cls.suffixes) if cls.suffixes else [cls.suffix]
        lowered = suffix.lower()
        return any(lowered == candidate.lower() for candidate in candidates)

    @classmethod
    def supports(cls, xml_path: Path, raw_text: str) -> bool:
        """判断给定 XML 是否适用于该解析器，默认基于后缀。"""

        return cls.check_suffix(xml_path.suffix.lower())

    @abstractclassmethod
    def open_file(cls, filepath: str):
        """载入并返回可供解析的对象（通常是 BeautifulSoup）。"""

    @abstractclassmethod
    def parsing(cls, file_bs):
        """解析并返回段落对象列表。"""

    @abstractclassmethod
    def get_metadata(cls, file_bs):
        """抽取文章元数据。"""
