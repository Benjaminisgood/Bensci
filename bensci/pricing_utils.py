from __future__ import annotations

"""
Pricing helpers tailored for the new Agents SDK workflow.

该文件仅搭建整体框架，便于未来接入实际的 Agents 事件。
所有需要 SDK 实例或回调的地方都用 TODO 标记，请按真实接口补全。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Literal, Optional, Protocol

import logging

LOGGER = logging.getLogger(__name__)

StepType = Literal["prompt", "completion"]


# ---------------------------------------------------------------------------
# 价格表与模型映射
# ---------------------------------------------------------------------------

DEFAULT_PRICING: Dict[str, Dict[StepType, float]] = {
    # TODO: 按需补齐常用模型价格（单位：美元 / 1K tokens）
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.003, "completion": 0.006},
}

MODEL_ALIASES: Dict[str, str] = {
    "gpt-4": "gpt-4o",
    "gpt-4-0613": "gpt-4o",
    "gpt-4o-2024-05-13": "gpt-4o",
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class StepRecord:
    model: str
    step_type: StepType
    tokens: int
    price_per_1k: float

    @property
    def cost(self) -> float:
        return self.tokens * self.price_per_1k / 1000


@dataclass
class InteractionLedger:
    """收集单次 Agent 运行的 token / 成本信息。"""

    steps: list[StepRecord] = field(default_factory=list)

    def add(self, record: StepRecord) -> None:
        LOGGER.debug("记录 Step: %s", record)
        self.steps.append(record)

    @property
    def total_cost(self) -> float:
        return sum(step.cost for step in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum(step.tokens for step in self.steps)

    def iter_breakdown(self) -> Iterable[StepRecord]:
        yield from self.steps


# ---------------------------------------------------------------------------
# Agent SDK 抽象
# ---------------------------------------------------------------------------

class AgentEvent(Protocol):
    """抽象代指 Agents SDK 里的事件对象。"""

    model: str
    # TODO: 填写事件实际属性（如 prompt_tokens、completion_tokens 等）


class AgentRunContext(Protocol):
    """抽象代指一次 Agent 运行上下文。"""

    id: str
    metadata: Dict[str, Any]
    # TODO: 如有需要可补充更多字段


# ---------------------------------------------------------------------------
# 价格工具核心
# ---------------------------------------------------------------------------

class PricingTable:
    """读写模型价格的实用类。"""

    def __init__(self, price_map: Optional[Dict[str, Dict[StepType, float]]] = None) -> None:
        self._price_map = price_map or dict(DEFAULT_PRICING)

    def resolve_model(self, model: str) -> str:
        canonical = MODEL_ALIASES.get(model, model)
        if canonical not in self._price_map:
            raise KeyError(f"未配置模型 {model} 的价格表，请更新 DEFAULT_PRICING。")
        return canonical

    def unit_price(self, model: str, step_type: StepType) -> float:
        canonical = self.resolve_model(model)
        return self._price_map[canonical][step_type]


class AgentTokenTracker:
    """
    监听 Agents SDK 的事件，汇总 token 用量与成本。

    用法（示例）：
        tracker = AgentTokenTracker()
        agent.on_event(tracker.observe_event)  # TODO: 根据实际 SDK 注册回调
        run_result = agent.run(...)
        ledger = tracker.flush()
    """

    def __init__(self, price_table: Optional[PricingTable] = None) -> None:
        self._price_table = price_table or PricingTable()
        self._ledger = InteractionLedger()
        self._current_run: Optional[str] = None

    def start_run(self, run: AgentRunContext) -> None:
        """在 Agent 运行开始时调用。"""
        LOGGER.debug("Agent run started: %s", getattr(run, "id", "<unknown>"))
        self._current_run = getattr(run, "id", None)
        self._ledger = InteractionLedger()

    def observe_event(self, event: AgentEvent) -> None:
        """监听事件并写入账本。"""
        model_name = getattr(event, "model", "")
        if not model_name:
            LOGGER.debug("忽略无模型信息的事件：%s", event)
            return

        # TODO: 从事件对象中提取 token 用量
        prompt_tokens = getattr(event, "prompt_tokens", None)
        completion_tokens = getattr(event, "completion_tokens", None)

        if prompt_tokens is not None:
            self._record_step(model_name, "prompt", int(prompt_tokens))
        if completion_tokens is not None:
            self._record_step(model_name, "completion", int(completion_tokens))

    def end_run(self, run: AgentRunContext) -> InteractionLedger:
        """运行结束时调用，返回账单。"""
        LOGGER.debug("Agent run finished: %s", getattr(run, "id", "<unknown>"))
        self._current_run = None
        return self._ledger

    def _record_step(self, model_name: str, step_type: StepType, tokens: int) -> None:
        if tokens < 0:
            LOGGER.warning("收到负数 token 数：%s，忽略。", tokens)
            return
        try:
            price = self._price_table.unit_price(model_name, step_type)
        except KeyError as exc:
            LOGGER.error("模型 %s 未配置价格：%s", model_name, exc)
            return
        self._ledger.add(StepRecord(model=model_name, step_type=step_type, tokens=tokens, price_per_1k=price))

    def flush(self) -> InteractionLedger:
        """返回当前账单并重置。"""
        ledger = self._ledger
        self._ledger = InteractionLedger()
        self._current_run = None
        return ledger


# ---------------------------------------------------------------------------
# 适配器（待补全）
# ---------------------------------------------------------------------------

class AgentsSDKAdapter:
    """
    该类示意如何把 token 统计器接入到 Agents SDK。

    TODO: 根据实际 SDK 的事件名称 / 回调机制替换示意方法。
    """

    def __init__(self) -> None:
        self.pricing_table = PricingTable()
        self.tracker = AgentTokenTracker(self.pricing_table)

    def bind_to_agent(self, agent: Any) -> None:
        """
        把 tracker 挂到实际的 agent 对象上。

        TODO: 使用 SDK 的 API 注册 start / event / end 回调。
        """
        # 伪代码示例：
        # agent.on("run_started", self.tracker.start_run)
        # agent.on("event", self.tracker.observe_event)
        # agent.on("run_finished", self.tracker.end_run)
        raise NotImplementedError("请根据 Agents SDK API 实现绑定逻辑")

    def summarize_cost(self) -> Dict[str, Any]:
        """返回上一轮运行的 Token/价格汇总。"""
        ledger = self.tracker.flush()
        return {
            "total_tokens": ledger.total_tokens,
            "total_cost": ledger.total_cost,
            "breakdown": [
                {
                    "model": step.model,
                    "step_type": step.step_type,
                    "tokens": step.tokens,
                    "unit_price": step.price_per_1k,
                    "cost": step.cost,
                }
                for step in ledger.iter_breakdown()
            ],
        }


__all__ = [
    "PricingTable",
    "StepRecord",
    "InteractionLedger",
    "AgentTokenTracker",
    "AgentsSDKAdapter",
]
