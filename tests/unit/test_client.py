"""Phase 1 TDD · TdxChronos facade scaffolding"""
import pytest

def test_tdx_client_can_be_imported():
    from tdx_chronos.client import TdxChronos
    assert TdxChronos is not None
