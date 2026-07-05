"""TDX-chronos · Alertor (v1.1 Sprint 5 T3)

§四.7 飞书告警 + DRY-RUN 卡片生成

公开 API:
- Alertor(chat_id, dry_run).send_card(title, blocks, tone)
- Alertor(chat_id, dry_run).send_alert(level, summary, detail)

实现:
- dry_run=True: 只 print 卡片 JSON 不真发 (默认)
- dry_run=False: 调用 OpenClaw message tool 发到飞书
- OpenClaw cron 模式下, message tool 不可用 → 必须 dry_run=False 走 stdout
  (cron delivery.mode=announce 会自动把 agent 输出转飞书)

使用场景:
  1. cron/daily_incr.sh 失败 → Alertor(dry_run=False).send_alert(level='error', ...)
  2. cron/weekly_doctor.sh unhealthy → Alertor(dry_run=False).send_alert(level='critical', ...)
  3. local dev → Alertor(dry_run=True).send_alert(...) → 仅 print
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# 飞书群 (默认 = 告警群 · 与 auto-commit 同群)
DEFAULT_ALERT_CHAT = "oc_812b4a80dbf93832f71b6135ef6cb25a"

# tone → emoji + color
TONE_INFO = "info"
TONE_SUCCESS = "success"
TONE_WARNING = "warning"
TONE_DANGER = "danger"
TONE_NEUTRAL = "neutral"

VALID_TONES = {TONE_INFO, TONE_SUCCESS, TONE_WARNING, TONE_DANGER, TONE_NEUTRAL}


@dataclass
class CardBlock:
    """飞书卡片 block"""

    type: str = "text"  # text | context | divider
    text: str = ""
    fields: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        if self.type == "divider":
            return {"type": "divider"}
        if self.type == "context":
            return {"type": "context", "fields": self.fields}
        return {"type": "text", "text": self.text}


@dataclass
class AlertCard:
    """完整飞书告警卡片"""

    title: str
    blocks: List[CardBlock]
    tone: str = TONE_INFO
    chat_id: str = DEFAULT_ALERT_CHAT
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "tone": self.tone,
            "chat_id": self.chat_id,
            "timestamp": self.timestamp.isoformat(),
            "blocks": [b.to_dict() for b in self.blocks],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class Alertor:
    """§四.7 飞书告警"""

    def __init__(
        self,
        chat_id: str = DEFAULT_ALERT_CHAT,
        dry_run: Optional[bool] = None,
    ) -> None:
        """
        Args:
            chat_id: 飞书群 chat_id
            dry_run: True=只 print 卡片 (默认从 TDX_DRY_RUN env var)
        """
        self.chat_id = chat_id
        if dry_run is None:
            dry_run = os.environ.get("TDX_DRY_RUN", "1") == "1"
        self.dry_run = dry_run

    def build_card(
        self,
        title: str,
        blocks: List[CardBlock],
        tone: str = TONE_INFO,
    ) -> AlertCard:
        """构造 AlertCard (不发送)"""
        if tone not in VALID_TONES:
            raise ValueError(f"Invalid tone: {tone}. Valid: {VALID_TONES}")
        return AlertCard(
            title=title,
            blocks=blocks,
            tone=tone,
            chat_id=self.chat_id,
        )

    def send_card(
        self,
        title: str,
        blocks: List[CardBlock],
        tone: str = TONE_INFO,
    ) -> AlertCard:
        """发送卡片 (dry_run=True 时只 print)"""
        card = self.build_card(title, blocks, tone)
        if self.dry_run:
            print(f"[Alertor DRY-RUN] {card.to_json()}")
            return card

        # 真发: 写 stdout 让 cron delivery 抓
        # OpenClaw cron isolated session 会自动把 stdout 投递到 delivery.channel
        print(f"[Alertor → {self.chat_id}] {card.to_json()}")
        # TODO v2.0: 调用 message tool 发飞书卡片 (需 OpenClaw runtime 集成)
        return card

    def send_alert(
        self,
        level: str,
        summary: str,
        detail: Optional[str] = None,
        source: Optional[str] = None,
    ) -> AlertCard:
        """高层 API: 1 行发告警

        Args:
            level:   'info' | 'success' | 'warning' | 'error' | 'critical'
            summary: 1 行总结 (≤ 80 chars)
            detail:  Optional 详细 (多行)
            source:  Optional 来源脚本名 (e.g. 'daily_incr.sh')

        Tone 映射:
            info/success → info/success
            warning      → warning
            error/critical → danger
        """
        tone_map = {
            "info": TONE_INFO,
            "success": TONE_SUCCESS,
            "warning": TONE_WARNING,
            "error": TONE_DANGER,
            "critical": TONE_DANGER,
        }
        tone = tone_map.get(level, TONE_INFO)

        title = f"🦞 tdx-chronos {level}: {summary[:60]}"
        blocks: List[CardBlock] = [
            CardBlock(type="text", text=f"**{summary}**"),
        ]
        if source:
            blocks.append(CardBlock(type="context", fields=[
                {"tag": "text", "text": f"source: {source}"},
            ]))
        if detail:
            blocks.append(CardBlock(type="divider"))
            blocks.append(CardBlock(type="text", text=detail))
        blocks.append(CardBlock(type="context", fields=[
            {"tag": "text", "text": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")},
        ]))

        return self.send_card(title, blocks, tone=tone)