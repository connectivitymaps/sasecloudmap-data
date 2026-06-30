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

    assert (
        catonetworks.normalize_location_text("Vancourver, CAN") == "Vancouver, Canada"
    )
    assert catonetworks.normalize_location_text("Toronto, CAN") == "Toronto, Canada"
    assert (
        catonetworks.normalize_location_text("Mexico City, MEX")
        == "Mexico City, Mexico"
    )
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


def test_cloudflare_output_uses_city_country_and_site_code(monkeypatch):
    cloudflare_geojson = import_provider_module(monkeypatch, "cloudflare_geojson")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "iata": "ZRH",
                    "city": " Zurich ",
                    "cca2": "CH",
                    "lat": 47.4647,
                    "lon": 8.5492,
                },
                {
                    "iata": "AGR",
                    "city": "",
                    "cca2": "IN",
                    "lat": 27.1767,
                    "lon": 78.0081,
                },
            ]

    monkeypatch.setattr(cloudflare_geojson.httpx, "get", lambda *_, **__: Response())

    locations = cloudflare_geojson.get_cloudflare_data()
    features = cloudflare_geojson.convert_to_geojson(locations)

    assert features[0]["properties"] == {
        "city": "Zurich",
        "countryCode": "CH",
        "siteCode": "ZRH",
    }
    assert features[1]["properties"] == {
        "city": "AGR",
        "countryCode": "IN",
        "siteCode": "AGR",
    }


def test_netskope_output_uses_city_country_and_site_code(monkeypatch):
    netskope_geojson = import_provider_module(monkeypatch, "netskope_geojson")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "name": "ZUR1",
                    "city": "Zurich",
                    "country_code": "CH",
                    "latitude": 47.4611,
                    "longitude": 8.553,
                    "is_dp": True,
                }
            ]

    monkeypatch.setattr(netskope_geojson.httpx, "get", lambda *_, **__: Response())

    locations = netskope_geojson.get_data()
    features = netskope_geojson.convert_to_geojson(locations)

    assert features[0]["properties"] == {
        "city": "Zurich",
        "countryCode": "CH",
        "siteCode": "ZUR1",
    }


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


def test_fortinet_extracts_rows_when_location_and_code_are_separate_columns(
    monkeypatch,
):
    fortinet_geojson = import_provider_module(monkeypatch, "fortinet_geojson")

    html = """
    <div id="mc-main-content">
      <table>
        <thead>
          <tr>
            <th>Cloud Location</th>
            <th>Code</th>
            <th>Analytics location Availability</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Fortinet</td>
            <td>Ashburn, Virginia (United States)</td>
            <td><p>IAD-F5</p></td>
            <td>Yes</td>
          </tr>
          <tr>
            <td>Fortinet</td>
            <td>Dubai (United Arab Emirates) To comply with UAE regulations</td>
            <td><p>DXB-F2</p></td>
            <td>Yes</td>
          </tr>
        </tbody>
      </table>
    </div>
    """

    assert fortinet_geojson.extract_location_rows(html) == [
        {
            "name": "Ashburn, Virginia (United States) (IAD-F5)",
            "airport_code": "IAD",
        },
        {"name": "Dubai (United Arab Emirates) (DXB-F2)", "airport_code": "DXB"},
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


def test_paloalto_skips_country_only_location_labels(monkeypatch):
    paloalto_geojson = import_provider_module(monkeypatch, "paloalto_geojson")

    html = """
    <html>
      <body>
        <table>
          <thead>
            <tr>
              <th>Compute Location</th>
              <th>Prisma Access Location</th>
              <th>City and Country</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Europe</td>
              <td>Netherlands</td>
              <td>Amsterdam, Netherlands\n, Netherlands</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    assert paloalto_geojson.extract_paloalto_locations(html) == [
        "Amsterdam, Netherlands",
    ]


def test_aws_extract_pop_rows_parses_regions_countries_and_cities(monkeypatch):
    aws_geojson = import_provider_module(monkeypatch, "aws_geojson")

    html = """
    <div id="points-of-presence-pops">
      <div data-rg-n="BodyText">
        <p><b>North America</b></p>
        <p><b>Canada:</b> Calgary (2), Montreal 3)</p>
        <p><b>United States: </b>Atlanta (29), Boston (6)</p>
        <p>&nbsp;</p>
        <p><b>South America</b></p>
        <p><b>Brazil:</b> Fortaleza (6), Guarulhos (16)</p>
        <p><b>Embedded Points of Presence (PoPs)</b></p>
        <p><b>Some Country:</b> Should not appear</p>
      </div>
    </div>
    """

    assert aws_geojson.extract_pop_rows(html) == [
        {"region": "North America", "country": "Canada", "city": "Calgary"},
        {"region": "North America", "country": "Canada", "city": "Montreal"},
        {"region": "North America", "country": "United States", "city": "Atlanta"},
        {"region": "North America", "country": "United States", "city": "Boston"},
        {"region": "South America", "country": "Brazil", "city": "Fortaleza"},
        {"region": "South America", "country": "Brazil", "city": "Guarulhos"},
    ]


def test_aws_extract_pop_rows_handles_singapore_and_malformed_blocks(monkeypatch):
    aws_geojson = import_provider_module(monkeypatch, "aws_geojson")

    html = """
    <div id="points-of-presence-pops">
      <div data-rg-n="BodyText">
        <p><b>North America</b></p>
        <p><b>Singapore</b> (12)</p>
        <p><b>Portugal:</b> LisbonRomania: Bucharest (3)</p>
      </div>
    </div>
    """

    assert aws_geojson.extract_pop_rows(html) == [
        {"region": "North America", "country": "Singapore", "city": "Singapore"},
        {"region": "North America", "country": "Portugal", "city": "Lisbon"},
        {"region": "North America", "country": "Romania", "city": "Bucharest"},
    ]


def test_aws_split_cities_splits_and_strips_counts(monkeypatch):
    aws_geojson = import_provider_module(monkeypatch, "aws_geojson")

    assert aws_geojson.split_cities(
        "Calgary (2), Montreal (3), Santiago de Queretaro (10)"
    ) == [
        "Calgary",
        "Montreal",
        "Santiago de Queretaro",
    ]


def test_aws_split_cities_handles_malformed_counts(monkeypatch):
    aws_geojson = import_provider_module(monkeypatch, "aws_geojson")

    assert aws_geojson.split_cities(
        "Minneapolis (5), Nashville 2), Newark, New York (26)"
    ) == [
        "Minneapolis",
        "Nashville",
        "Newark",
        "New York",
    ]


def test_aws_parse_city_name_trims_whitespace_and_commas(monkeypatch):
    aws_geojson = import_provider_module(monkeypatch, "aws_geojson")

    assert aws_geojson.parse_city_name("Lisbon,") == "Lisbon"
    assert aws_geojson.parse_city_name("  Singapore  ") == "Singapore"
    assert aws_geojson.parse_city_name("  ") is None


def test_aws_geocode_city_uses_nominatim(monkeypatch):
    aws_geojson = import_provider_module(monkeypatch, "aws_geojson")

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "lat": "51.0504",
                    "lon": "13.7373",
                    "address": {"country_code": "de"},
                }
            ]

    monkeypatch.setattr(aws_geojson, "nominatim_get", lambda *_, **__: Response())
    monkeypatch.setattr(aws_geojson.time, "sleep", lambda _: None)

    assert aws_geojson.geocode_city("Berlin", "Germany") == {
        "name": "Berlin",
        "coordinates": ["51.0504", "13.7373"],
        "countryCode": "DE",
    }
