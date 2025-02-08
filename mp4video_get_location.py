import xml.etree.ElementTree as ET

def get_location_from_rdf(rdf, log_message):
    """Extract location data from RDF data."""
    location_data = {
        'location': None,
        'city': None,
        'state': None,
        'country': None,
        'gps': None
    }
    
    log_message("Looking for location data in XMP metadata...")
    
    # Find the rdf:Description element
    desc = rdf.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
    if desc is not None:
        log_message("Found rdf:Description element")
        
        # Check attributes with correct namespaces
        log_message("Checking location attributes...")
        location_keys = {
            'location': ['{http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/}Location'],
            'city': ['{http://ns.adobe.com/photoshop/1.0/}City'],
            'state': ['{http://ns.adobe.com/photoshop/1.0/}State'],
            'country': ['{http://ns.adobe.com/photoshop/1.0/}Country']
        }
        
        # Try each field
        for field, keys in location_keys.items():
            for key in keys:
                if key in desc.attrib:
                    value = desc.attrib[key]
                    location_data[field] = value
                    log_message(f"✓ Found {field}: '{value}'")
                else:
                    log_message(f"  Checked {field} attribute: not found")
        
        # Check for GPS coordinates with both possible namespaces
        gps_keys = {
            'lat': ['{http://ns.adobe.com/exif/1.0/}GPSLatitude'],
            'lon': ['{http://ns.adobe.com/exif/1.0/}GPSLongitude']
        }
        
        lat = None
        lon = None
        
        for key in gps_keys['lat']:
            if key in desc.attrib:
                lat = desc.attrib[key]
                log_message(f"Found latitude: {lat}")
                break
                
        for key in gps_keys['lon']:
            if key in desc.attrib:
                lon = desc.attrib[key]
                log_message(f"Found longitude: {lon}")
                break
        
        if lat and lon:
            # Keep the original format from the XMP
            location_data['gps'] = f"{lat}, {lon}"
            log_message(f"✓ Found GPS coordinates: {location_data['gps']}")
            
    else:
        log_message("✗ No rdf:Description element found")
    
    # Log summary of found location data
    found_fields = [f"{field}: '{value}'" for field, value in location_data.items() if value is not None]
    if found_fields:
        log_message("=== Location Data Summary ===")
        for field in found_fields:
            log_message(f"  {field}")
    else:
        log_message("No location data found in XMP")
    
    return location_data
