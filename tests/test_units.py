from raycast_linux.logic.units import try_convert


def test_temperature():
    assert try_convert("100 c f") == "212 f"
    assert try_convert("32 f c") == "0 c"
    assert try_convert("0 c k") == "273.15 k"
    assert try_convert("273.15 k c") == "0 c"


def test_length():
    assert try_convert("1 km m") == "1000 m"
    assert try_convert("1 mi km") == "1.609344 km"
    assert try_convert("1 ft in") == "12 in"
    assert try_convert("5 km mi") == "3.10685596 mi"


def test_mass_volume_time_speed():
    assert try_convert("1 kg g") == "1000 g"
    assert try_convert("1 lb kg") == "0.45359237 kg"
    assert try_convert("1 l ml") == "1000 ml"
    assert try_convert("1 gal l") == "3.78541178 l"
    assert try_convert("1 h min") == "60 min"
    assert try_convert("60 min h") == "1 h"
    assert try_convert("1 mph kmh") == "1.609344 kmh"


def test_rejects():
    assert try_convert("5 c") is None
    assert try_convert("5 x y") is None
    assert try_convert("5 c c") is None
    assert try_convert("hello") is None
    assert try_convert("") is None
