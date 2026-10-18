"""``tracebi connect``: secrets stay in ``.env``, a failed test writes nothing."""


from tracebi.cli import main


def _run(monkeypatch, tmp_path, *argv):
    monkeypatch.chdir(tmp_path)
    return main(list(argv))


class TestConnectFlags:


    def test_failing_test_writes_nothing(self, tmp_path, monkeypatch, capsys):
        missing = tmp_path / "missing.duckdb"
        code = _run(
            monkeypatch, tmp_path,
            "connect", "wh", "--kind", "duckdb", "--database", str(missing),
        )
        assert code == 1
        err = capsys.readouterr().err
        assert "FileNotFoundError" in err or "does not exist" in err
        assert not (tmp_path / ".env").exists()
        assert not (tmp_path / "models").exists()
        assert not (tmp_path / ".gitignore").exists()

    def test_existing_env_key_is_not_overwritten_without_force(self, tmp_path, monkeypatch, capsys):
        db = tmp_path / "wh.duckdb"
        import duckdb
        duckdb.connect(str(db)).close()
        (tmp_path / ".env").write_text("OTHER=keep\nTRACEBI_WH_DATABASE=old-value\n")
        code = _run(
            monkeypatch, tmp_path,
            "connect", "--python", "wh", "--kind", "duckdb", "--database", str(db),
        )
        assert code == 1
        text = (tmp_path / ".env").read_text()
        assert "OTHER=keep" in text
        assert "old-value" in text
        assert str(db) not in text
        assert not (tmp_path / "models" / "_connections" / "wh.py").exists()
        captured = capsys.readouterr()
        assert "old-value" not in captured.out
        assert str(db) not in captured.out


    def test_secret_never_appears_in_stdout_or_the_module(self, tmp_path, monkeypatch, capsys):
        url = "postgresql://analyst:s3cret-token@localhost:5432/sales"
        code = _run(
            monkeypatch, tmp_path,
            "connect", "--python", "wh", "--kind", "postgres", "--url", url, "--no-test",
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "s3cret-token" not in captured.out
        assert "s3cret-token" not in captured.err
        src = (tmp_path / "models" / "_connections" / "wh.py").read_text()
        assert "s3cret-token" not in src
        assert "os.environ" in src
        assert "load_dotenv" in src
        assert "s3cret-token" in (tmp_path / ".env").read_text()
        assert "TRACEBI_WH_URL" in (tmp_path / ".env").read_text()
