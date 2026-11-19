from scripts.load_data import clean_column


def test_clean_column_names():
    seen: set[str] = set()
    assert clean_column("Account ID", seen) == "account_id"
    assert clean_column("Account-ID", seen) == "account_id_2"
    assert clean_column("1st Contact", seen) == "c_1st_contact"
    assert clean_column("", seen) == "col"
