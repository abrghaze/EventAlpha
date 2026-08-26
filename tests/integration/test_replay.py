from app.config import Settings
from app.replay import demo_signal


def test_replay_path_is_paper_safe() -> None:
    signal = demo_signal(Settings("test", True, False, False))
    assert signal.symbol == "ACME"
    assert signal.risk.policy_version == "paper-risk-v0.1.0"
    assert "no paper order" in signal.summary.lower()
