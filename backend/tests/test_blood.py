from datetime import date, timedelta

from app.blood import compatible_donor_groups, find_hospital, haversine_km, in_cooldown, is_compatible, zone_for


def test_universal_donor_and_recipient():
    assert is_compatible("O-", "AB+") and is_compatible("O-", "B-")
    assert len(compatible_donor_groups("AB+")) == 8
    assert compatible_donor_groups("O-") == ["O-"]


def test_incompatible_pairs():
    assert not is_compatible("A+", "B+")
    assert not is_compatible("B+", "B-")  # Rh+ cannot go to Rh-
    assert not is_compatible("AB+", "O+")


def test_cooldown_male_female():
    today = date(2026, 6, 1)
    assert in_cooldown(today - timedelta(days=80), "M", today)
    assert not in_cooldown(today - timedelta(days=95), "M", today)
    assert in_cooldown(today - timedelta(days=100), "F", today)  # women: 120 days
    assert not in_cooldown(None, "F", today)


def test_geo():
    assert 4 < haversine_km(12.9592, 77.6489, 12.9298, 77.6197) < 6
    assert zone_for(12.9716, 77.5946) == "central"
    assert find_hospital("ನನಗೆ ಮಣಿಪಾಲ ಆಸ್ಪತ್ರೆ")["name"].startswith("Manipal")
