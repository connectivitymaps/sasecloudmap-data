def geojson_skeleton(data):
    """generate geojson skeleton"""
    skeleton = {"type": "FeatureCollection", "features": data}
    return skeleton
