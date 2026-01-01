import pytest
from src.domain.models.geo import GeoPoint


def test_geo_point_accepts_valid_coordinates() -> None:
    p = GeoPoint(lat=28.1234, lon=-15.4321)
    assert p.lat == 28.1234
    assert p.lon == -15.4321


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (-90.0001, 0.0),
        (90.0001, 0.0),
        (0.0, -180.0001),
        (0.0, 180.0001),
    ],
)
def test_geo_point_rejects_out_of_range_coordinates(lat: float, lon: float) -> None:
    with pytest.raises(ValueError):
        GeoPoint(lat=lat, lon=lon)
