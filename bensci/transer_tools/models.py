"""
基于旧版 llm_miner.schema 改造的轻量数据模型定义。

为了方便后续硬检索与软检索，这里把全文解析后的核心结构
（元数据、段落对象、段落集合）集中到一个文件中，并添加中文注释。
"""

from __future__ import annotations

import copy
import json
import pprint
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    """用于描述文献层面的基本信息。"""

    doi: Optional[str] = None
    title: Optional[str] = None
    journal: Optional[str] = None
    date: Optional[str] = None
    author_list: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """导出为 Python 字典，方便序列化或 DataFrame 处理。"""
        return {
            "doi": self.doi,
            "title": self.title,
            "journal": self.journal,
            "date": self.date,
            "author_list": self.author_list,
        }


class Paragraph(BaseModel):
    """
    用于表示单个段落（或图/表描述等元素）。

    - idx: 在文章中的顺序编号。
    - type: text/table/figure 等分类。
    - clean_text: 清洗后的纯文本，硬检索和嵌入都会依赖这个字段。
    """

    idx: Union[int, str]
    type: str
    classification: Optional[Any] = None
    content: str
    clean_text: Optional[str] = None
    data: Optional[List[Any]] = None
    include_properties: Optional[Any] = None
    intermediate_step: Dict[str, Any] = dict()

    def merge(self, others: "Paragraph", merge_idx: bool = False) -> None:
        """把短段落并入上一段，保持结构与旧版解析器一致。"""
        if merge_idx:
            self.idx = f"{self.idx}, {others.idx}"
        self.content += others.content
        if self.clean_text and others.clean_text:
            self.clean_text += "\n\n" + others.clean_text

        if isinstance(others.data, list):
            if isinstance(self.data, list):
                self.data += others.data
            else:
                self.data = others.data

    def has_data(self) -> bool:
        return bool(self.data) and self.data != "None"

 
    def to_json(self, filepath: str) -> None:
        """保存到磁盘，方便调试。"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def print(self) -> None:
        """人类可读的调试输出。"""
        string = (
            f"Idx : {self.idx}\n"
            f"Type : {self.type}\n"
            f"Classification: {self.classification}\n"
            f"Content: \n{self.clean_text}\n"
            f"Include Properties : {self.include_properties}\n"
            f"Data :\n{pprint.pformat(self.data, sort_dicts=False)}"
        )
        print(string)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Paragraph":
        return cls(
            idx=data["idx"],
            type=data["type"],
            classification=data.get("classification"),
            content=data["content"],
            clean_text=data.get("clean_text"),
            data=data.get("data"),
            include_properties=data.get("include_properties"),
            intermediate_step=data.get("intermediate_step", dict()),
        )


class Elements(Sequence, BaseModel):
    """段落序列的轻量封装，提供一些筛选工具方法。"""

    elements: List[Paragraph]

    def __getitem__(self, idx: int) -> Paragraph:
        return self.elements[idx]

    def __len__(self) -> int:
        return len(self.elements)

    def __bool__(self) -> bool:
        return bool(self.elements)

    def append(self, para: Paragraph) -> None:
        self.elements.append(para)

    def get_texts(self) -> List[Paragraph]:
        return [e for e in self.elements if e.type == "text"]

    def get_tables(self) -> List[Paragraph]:
        return [e for e in self.elements if e.type == "table"]

    def get_figures(self) -> List[Paragraph]:
        return [e for e in self.elements if e.type == "figure"]

    def to_dict(self) -> List[Dict[str, Any]]:
        return [para.to_dict() for para in self.elements]

    def to_json(self, filepath: str) -> None:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def empty(cls) -> "Elements":
        return cls(elements=list())

    @classmethod
    def from_dict(cls, data: List[Dict[str, Any]]) -> "Elements":
        return cls(elements=[Paragraph.from_dict(d) for d in data])

    @classmethod
    def from_json(cls, filepath: str) -> "Elements":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


class DocumentBlock(BaseModel):
    """标准化后用于写入 JSON 的块结构。"""

    idx: str
    type: str
    content: str
    table: Optional[Dict[str, Any]] = None
    figure: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"idx": self.idx, "type": self.type, "content": self.content}
        if self.table:
            data["table"] = self.table
        if self.figure:
            data["figure"] = self.figure
        if self.metadata:
            data["metadata"] = self.metadata
        return data


class StructuredDocument(BaseModel):
    """解析完成后的一篇文章，包含元数据和块列表。"""

    metadata: Metadata
    blocks: List[DocumentBlock]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "blocks": [block.to_dict() for block in self.blocks],
        }

    def to_json(self, path: Path) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
