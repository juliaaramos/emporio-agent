from emporio import db
from emporio.data_quality import FLAG_REVIEW, check_products, full_report
from emporio.ingest import read_raw


def test_flags_exactly_the_auto_generated_block():
    checks = check_products(read_raw()["products"])
    flagged = {pid for pid, c in checks.items() if c.flagged}
    assert flagged == set(range(135, 145))


def test_brand_mismatch_detected_in_the_seven_known_products():
    checks = check_products(read_raw()["products"])
    mismatch = {pid for pid, c in checks.items() if any("marca do nome" in r for r in c.reasons)}
    assert mismatch == {135, 136, 137, 139, 140, 142, 144}


def test_spec_contradictions():
    checks = check_products(read_raw()["products"])
    assert any("5 cordas" in r for r in checks[137].reasons)
    assert any("poplar" in r for r in checks[139].reasons)
    assert any("88 teclas" in r for r in checks[142].reasons)


def test_flag_is_persisted_and_raw_is_untouched():
    row = db.query_one("SELECT data_quality_flag FROM products WHERE product_id=137")
    assert row["data_quality_flag"] == FLAG_REVIEW
    assert db.query_one("SELECT data_quality_flag FROM products WHERE product_id=95")["data_quality_flag"] is None
    raw_header = (read_raw()["products"][0]).keys()
    assert "data_quality_flag" not in raw_header


def test_report_covers_known_issues():
    report = "\n".join(full_report(read_raw()))
    for expected in [
        "[pedido 3] total gravado 3450",
        "[pedido 20] total gravado 1400",
        "[produto 136] descontinuado com 13",
        "[pedido 3] entregue com produto 130",
        "bruno.martins@jmail.com compartilhado pelos clientes 11, 43",
        "[produto 96] ativo com estoque zero",
    ]:
        assert expected in report
