from src.sponsor_checker import check_company_sponsor, find_positive_sponsorship_phrase


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


def test_multi_word_company_requires_all_words_to_match():
    rows = [
        {"Organisation Name": "London Tech Limited"},
        {"Organisation Name": "ABC Partners LLP"},
        {"Organisation Name": "London Partners Limited"},
    ]

    result = check_company_sponsor("London Partners", rows, {})

    assert result.status == "found"
    assert result.confidence == "high"
    assert result.matched_name == "London Partners Limited"
    assert len(result.matched_rows) == 1


def test_optional_group_word_not_required():
    rows = [{"Organisation Name": "Woodstock Limited"}]

    result = check_company_sponsor("Woodstock Group", rows, {})

    assert result.status == "found"
    assert result.confidence == "high"
    assert result.matched_name == "Woodstock Limited"


def test_agency_list_match_returns_agency():
    result = check_company_sponsor(
        "Harnham",
        [{"Organisation Name": "Harnham Search and Selection Limited"}],
        {},
        agency_checker=lambda company_name: company_name.lower() == "harnham",
    )

    assert result.status == "agency"
    assert result.confidence == "high"
    assert result.matched_by == "agency_list"


def test_manual_sponsor_override_takes_precedence_over_agency_and_sponsor_list():
    result = check_company_sponsor(
        "Harnham",
        [{"Organisation Name": "Harnham Search and Selection Limited"}],
        {},
        agency_checker=lambda company_name: True,
        sponsor_override_lookup=lambda company_name: {
            "company_name": company_name,
            "sponsor_status": "self_confirmed",
        },
    )

    assert result.status == "self_confirmed"
    assert result.confidence == "high"
    assert result.matched_by == "manual_sponsor"


def test_positive_sponsorship_phrase_is_detected():
    phrase = find_positive_sponsorship_phrase("Benefits include visa sponsorship available for this role.")

    assert phrase == "visa sponsorship available"


def test_negative_sponsorship_phrase_is_not_positive():
    phrase = find_positive_sponsorship_phrase("No visa sponsorship available for this role.")

    assert phrase is None


def test_custom_positive_sponsorship_phrase_can_be_configured():
    phrase = find_positive_sponsorship_phrase(
        "This role includes Skilled Worker support for the right candidate.",
        positive_patterns=[r"skilled worker support"],
        negative_patterns=[],
    )

    assert phrase == "skilled worker support"


def test_invalid_regex_pattern_falls_back_to_phrase_matching():
    phrase = find_positive_sponsorship_phrase(
        "The package includes c++ visa support.",
        positive_patterns=["c++ visa support"],
        negative_patterns=[],
    )

    assert phrase == "c++ visa support"


def test_single_generic_word_does_not_return_high_confidence_match():
    rows = [
        {"Organisation Name": "ABC Partners LLP"},
        {"Organisation Name": "XYZ Partners Limited"},
    ]

    result = check_company_sponsor("Partners", rows, {})

    assert result.status == "not_found"
    assert result.confidence == "low"
