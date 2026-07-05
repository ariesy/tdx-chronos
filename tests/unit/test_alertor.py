"""Sprint 5 T3 · alertor.py 单元测试

5 测试:
- dry-run 默认 + 自定义
- 卡片格式校验
- 4 种 tone (info/success/warning/danger)
- send_alert 高层 API
- 默认 chat_id
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from tdx_chronos.alertor import (
    AlertCard,
    Alertor,
    CardBlock,
    DEFAULT_ALERT_CHAT,
    TONE_DANGER,
    TONE_INFO,
    TONE_NEUTRAL,
    TONE_SUCCESS,
    TONE_WARNING,
)


class TestAlertorDryRun:
    def test_dry_run_default_true(self, monkeypatch):
        """默认 dry_run=True (TDX_DRY_RUN env 默认 '1')"""
        monkeypatch.delenv("TDX_DRY_RUN", raising=False)
        a = Alertor()
        assert a.dry_run is True

    def test_dry_run_explicit_false(self):
        a = Alertor(dry_run=False)
        assert a.dry_run is False

    def test_dry_run_env_override(self, monkeypatch):
        monkeypatch.setenv("TDX_DRY_RUN", "0")
        a = Alertor()
        assert a.dry_run is False

    def test_send_card_dry_run_prints(self, capsys, monkeypatch):
        """DRY-RUN 模式: 只 print 卡片 JSON, 不真发"""
        monkeypatch.delenv("TDX_DRY_RUN", raising=False)
        a = Alertor()
        blocks = [CardBlock(type="text", text="hello")]
        card = a.send_card("test", blocks, tone=TONE_INFO)
        captured = capsys.readouterr()
        assert "[Alertor DRY-RUN]" in captured.out
        assert "test" in captured.out


class TestAlertCardFormat:
    def test_invalid_tone_raises(self):
        a = Alertor(dry_run=True)
        with pytest.raises(ValueError, match="Invalid tone"):
            a.build_card("x", [], tone="bad-tone")

    def test_card_to_dict(self):
        blocks = [
            CardBlock(type="text", text="line1"),
            CardBlock(type="divider"),
            CardBlock(type="context", fields=[{"tag": "text", "text": "ctx"}]),
        ]
        a = Alertor(dry_run=True)
        card = a.build_card("title", blocks, tone=TONE_INFO)
        d = card.to_dict()
        assert d["title"] == "title"
        assert d["tone"] == TONE_INFO
        assert len(d["blocks"]) == 3
        assert d["blocks"][1]["type"] == "divider"

    def test_card_to_json_unicode(self):
        blocks = [CardBlock(type="text", text="中文测试")]
        a = Alertor(dry_run=True)
        card = a.build_card("测试", blocks)
        j = card.to_json()
        assert "中文测试" in j
        # 验证 JSON 合法
        parsed = json.loads(j)
        assert parsed["title"] == "测试"


class TestAlertorSendAlert:
    def test_send_alert_info(self, capsys):
        """send_alert level=info → TONE_INFO"""
        a = Alertor(dry_run=True)
        card = a.send_alert("info", "test summary")
        assert card.tone == TONE_INFO

    def test_send_alert_warning(self, capsys):
        a = Alertor(dry_run=True)
        card = a.send_alert("warning", "test")
        assert card.tone == TONE_WARNING

    def test_send_alert_error_to_danger(self, capsys):
        """level=error → TONE_DANGER"""
        a = Alertor(dry_run=True)
        card = a.send_alert("error", "test")
        assert card.tone == TONE_DANGER

    def test_send_alert_critical_to_danger(self, capsys):
        a = Alertor(dry_run=True)
        card = a.send_alert("critical", "test")
        assert card.tone == TONE_DANGER

    def test_send_alert_success(self, capsys):
        a = Alertor(dry_run=True)
        card = a.send_alert("success", "test", detail="details")
        assert card.tone == TONE_SUCCESS

    def test_send_alert_with_source_and_detail(self, capsys):
        """source + detail 都应进卡片"""
        a = Alertor(dry_run=True)
        card = a.send_alert("error", "summary", detail="line1\nline2", source="daily_incr.sh")
        assert any(b.text == "**summary**" for b in card.blocks)
        assert any(b.fields for b in card.blocks if b.type == "context")
        # detail 应在某个 text block 中
        all_texts = " ".join(b.text for b in card.blocks if b.type == "text")
        assert "line1" in all_texts
        assert "line2" in all_texts


class TestAlertorDefaultChat:
    def test_default_chat_id(self):
        """默认 chat_id = 告警群"""
        a = Alertor()
        assert a.chat_id == DEFAULT_ALERT_CHAT

    def test_custom_chat_id(self):
        a = Alertor(chat_id="oc_custom_chat")
        assert a.chat_id == "oc_custom_chat"


class TestAllTones:
    def test_all_5_tones_valid(self):
        a = Alertor(dry_run=True)
        for tone in (TONE_INFO, TONE_SUCCESS, TONE_WARNING, TONE_DANGER, TONE_NEUTRAL):
            card = a.build_card("x", [], tone=tone)
            assert card.tone == tone