from bench.evidence import line_evidence, product_name


def L(sku, color, size):
    return {"sku": sku, "color": color, "size": size, "qty": 1, "unit_price": 1}


def test_guessed_product_is_flagged():
    email = "We need 200 stainless steel water bottles, silver, with our logo."
    probs = line_evidence(L("TB-200", "Silver", "N/A"), email)
    assert any("Drawstring Backpack" in p and "guessed" in p for p in probs)
    assert product_name("TB-200") == "Drawstring Backpack"


def test_informal_names_and_codes_count_as_evidence():
    assert line_evidence(L("HD-100", "Maroon", "XL"), "a dozen maroon pullover hoodys in XL") == []
    assert line_evidence(L("CP-200", "Navy", "N/A"), "60 navy knit beenies") == []
    assert line_evidence(L("MG-100", "White", "N/A"), "48 White mugs (MG-100)") == []
    assert line_evidence(L("TS-200", "Heather Gray", "2XL"), "heather grey premium tees: 2xl x 10") == []
    assert line_evidence(L("HD-100", "Black", "S"), "pullover hoodies in black: 4 small, 6 medium") == []


def test_wrong_size_is_flagged_with_what_the_email_says():
    probs = line_evidence(L("TS-100", "Navy", "2XL"), "30 Navy Classic Cotton Tees (TS-100) in size 3XL.")
    assert probs == ["size 2XL is not in the email (email says 3XL)"]
