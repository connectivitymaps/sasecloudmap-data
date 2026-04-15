import importlib
import sys
from pathlib import Path


PROVIDER_DIR = Path(__file__).resolve().parent.parent / "provider_data"


def import_provider_module(monkeypatch, module_name: str):
    monkeypatch.syspath_prepend(str(PROVIDER_DIR))
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_cato_prefers_serviced_through_geo_location(monkeypatch):
    catonetworks = import_provider_module(monkeypatch, "catonetworks")

    csv_text = """Region,PoP\xa0Location,IP\xa0Range,Serviced Through (for Geo Location)\nGeo-Localized Ips,Albania,1-2,Milan\nAsia,\"Auckland, NZ\",1-2,\nGeo-Localized Ips,Bahamas,1-2,Miami\n"""

    assert catonetworks.extract_location_rows(csv_text) == [
        {"display_name": "Milan", "geocode_query": "Milan"},
        {"display_name": "Auckland, NZ", "geocode_query": "Auckland, NZ"},
        {"display_name": "Miami", "geocode_query": "Miami"},
    ]


def test_cato_normalizes_known_city_and_country_aliases(monkeypatch):
    catonetworks = import_provider_module(monkeypatch, "catonetworks")

    assert catonetworks.normalize_location_text("Vancourver, CAN") == "Vancouver, Canada"
    assert catonetworks.normalize_location_text("Toronto, CAN") == "Toronto, Canada"
    assert catonetworks.normalize_location_text("Mexico City, MEX") == "Mexico City, Mexico"
    assert catonetworks.normalize_location_text("Quito, ECUA") == "Quito, Ecuador"


def test_checkpoint_normalization_keeps_pop_numbers_and_removes_footnotes(monkeypatch):
    checkpoint_geojson = import_provider_module(monkeypatch, "checkpoint_geojson")

    assert (
        checkpoint_geojson.normalize_location_text("Ashburn 1, VA, USA (1)")
        == "Ashburn 1, VA, USA"
    )
    assert (
        checkpoint_geojson.normalize_location_text("New York 3, NY, USA(1)")
        == "New York 3, NY, USA"
    )


def test_checkpoint_build_geocode_queries_strips_pop_numbers(monkeypatch):
    checkpoint_geojson = import_provider_module(monkeypatch, "checkpoint_geojson")

    assert checkpoint_geojson.build_geocode_queries("Ashburn 1, VA, USA") == [
        "Ashburn, VA, United States"
    ]
    assert checkpoint_geojson.build_geocode_queries("London 3, UK") == [
        "London, United Kingdom"
    ]


def test_cisco_uses_facility_name_before_falling_back_to_location(monkeypatch):
    cisco_umbrella_geojson = import_provider_module(
        monkeypatch, "cisco_umbrella_geojson"
    )

    assert cisco_umbrella_geojson.build_geocode_queries(
        "Ashburn, US", "Equinix Ashburn"
    ) == ["Equinix Ashburn, Ashburn, US", "Ashburn, US"]


def test_fortinet_keeps_multiple_facilities_for_same_airport_code(monkeypatch):
    fortinet_geojson = import_provider_module(monkeypatch, "fortinet_geojson")

    html = """
    <div id="mc-main-content">
      <table>
        <tr><td class="TableStyle-FortinetTable-BodyE-Column2-Body1">Dubai - United Arab Emirates (DXB-F1)</td></tr>
        <tr><td class="TableStyle-FortinetTable-BodyE-Column2-Body2"><p>Dubai - United Arab Emirates (DXB-F2)</p></td></tr>
      </table>
    </div>
    """

    assert fortinet_geojson.extract_location_rows(html) == [
        {"name": "Dubai - United Arab Emirates (DXB-F1)", "airport_code": "DXB"},
        {"name": "Dubai - United Arab Emirates (DXB-F2)", "airport_code": "DXB"},
    ]


def test_fortinet_normalization_trims_footnotes_and_notes(monkeypatch):
    fortinet_geojson = import_provider_module(monkeypatch, "fortinet_geojson")

    assert (
        fortinet_geojson.normalize_location_text("Ottawa - Canada (YOW-F1) 3")
        == "Ottawa - Canada (YOW-F1)"
    )
    assert (
        fortinet_geojson.normalize_location_text(
            "Dubai - United Arab Emirates (DXB-F2) To comply with UAE regulations"
        )
        == "Dubai - United Arab Emirates (DXB-F2)"
    )


def test_iboss_normalization_removes_pop_suffix_and_number(monkeypatch):
    iboss_geojson = import_provider_module(monkeypatch, "iboss_geojson")

    assert iboss_geojson.normalize_pop_location("Dallas, TX POP 2") == "Dallas, TX"
    assert iboss_geojson.normalize_pop_location("Tianjin, CN POP 1") == "Tianjin, CN"


def test_paloalto_finds_locations_table_without_brittle_generated_id(monkeypatch):
    paloalto_geojson = import_provider_module(monkeypatch, "paloalto_geojson")

    html = """
    <html>
      <body>
        <table id="different-generated-id">
          <thead>
            <tr>
              <th>Compute Location</th>
              <th>Prisma Access Location</th>
              <th>City and Country</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Asia Northeast</td>
              <td>Japan Central</td>
              <td>Tokyo, Japan\nOsaka, Japan</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    assert paloalto_geojson.extract_paloalto_locations(html) == [
        "Tokyo, Japan",
        "Osaka, Japan",
    ]
