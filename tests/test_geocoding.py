def test_nominatim_headers_identify_application():
    from provider_data.utils.geocoding import nominatim_headers

    headers = nominatim_headers()

    assert "User-Agent" in headers
    assert "httpx" not in headers["User-Agent"].lower()
    assert "sasecloudmap" in headers["User-Agent"].lower()
