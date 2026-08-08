from types import SimpleNamespace

import police_thief.services.network_match as network_match


def test_complete_unverified_bundle_is_forwarded_in_real_email_mode(
    tmp_path, monkeypatch,
) -> None:
    required = [
        tmp_path / "declaration_G1.json",
        tmp_path / "config_G1_g01.json",
        tmp_path / "log_G1_g01.json",
        tmp_path / "result_G1.json",
    ]
    for path in required:
        path.write_text("{}", encoding="utf-8")
    delivered = []
    monkeypatch.setattr(
        network_match,
        "_try_email_submission",
        lambda paths, params, settings, emit: delivered.append(list(paths)),
    )
    messages = []

    sent = network_match._deliver_unverified_submission(
        required, object(), SimpleNamespace(email_mode="real"), messages.append,
    )

    assert sent is True
    assert delivered == [required]
    assert any("no values were fabricated or confirmed" in item for item in messages)


def test_unverified_bundle_is_not_sent_when_a_required_file_is_missing(
    tmp_path, monkeypatch,
) -> None:
    required = [tmp_path / "declaration_G1.json", tmp_path / "result_G1.json"]
    required[0].write_text("{}", encoding="utf-8")
    delivered = []
    monkeypatch.setattr(
        network_match,
        "_try_email_submission",
        lambda *args: delivered.append(args),
    )

    sent = network_match._deliver_unverified_submission(
        required, object(), SimpleNamespace(email_mode="real"), lambda _message: None,
    )

    assert sent is False
    assert delivered == []
