from src.sponsor_checker import check_company_sponsor


def test_direct_sponsor_match():
    rows = [{"Organisation Name": "Acme Software Limited", "Town/City": "London"}]

    result = check_company_sponsor("Acme Software", rows, {})

    assert result.status == "found"
    assert result.confidence == "high"
    assert result.matched_by == "direct"
    assert result.matched_name == "Acme Software Limited"
    assert "Acme Software Limited" in result.matched_rows[0]


def test_alias_sponsor_match_for_ey():
    rows = [{"Organisation Name": "Ernst & Young LLP"}]
    aliases = {"ey": ["ernst & young", "ernst and young", "ernst & young llp"]}

    result = check_company_sponsor("EY UK", rows, aliases)

    assert result.status == "found"
    assert result.confidence == "high"
    assert result.matched_by == "alias"
    assert result.matched_name == "Ernst & Young LLP"


def test_alias_sponsor_match_for_pwc():
    rows = [{"Organisation Name": "PricewaterhouseCoopers LLP"}]
    aliases = {"pwc": ["pricewaterhousecoopers", "pricewaterhousecoopers llp"]}

    result = check_company_sponsor("PwC UK", rows, aliases)

    assert result.status == "found"
    assert result.confidence == "high"
    assert result.matched_by == "alias"
    assert result.matched_name == "PricewaterhouseCoopers LLP"


def test_alias_sponsor_match_for_admiral_to_eui():
    rows = [{"Organisation Name": "EUI Limited"}]
    aliases = {"admiral": ["eui", "eui limited", "admiral group", "admiral insurance"]}

    result = check_company_sponsor("Admiral Insurance", rows, aliases)

    assert result.status == "found"
    assert result.confidence == "high"
    assert result.matched_by == "alias"
    assert result.matched_name == "EUI Limited"


def test_missing_company_returns_not_found():
    rows = [{"Organisation Name": "Known Sponsor Limited"}]

    result = check_company_sponsor("Missing Company", rows, {})

    assert result.status == "not_found"
    assert result.confidence == "low"
    assert result.matched_by == "none"
