import webbrowser
import requests
import folium
from flask import Flask

app = Flask(__name__)

# ==========================================================
# PUNE LOCATION
# ==========================================================

PUNE_LAT = 18.5204
PUNE_LON = 73.8567

# Approximate Pune District bounding box
# South, West, North, East
PUNE_BBOX = "18.15,73.35,19.25,74.10"


# ==========================================================
# OVERPASS API SERVERS
# ==========================================================

OVERPASS_SERVERS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter"
]


# ==========================================================
# OVERPASS QUERY
# ==========================================================

QUERY = f"""
[out:json][timeout:180];

(
    /* ==========================================
       EMERGENCY INFRASTRUCTURE
       ========================================== */

    nwr["amenity"="hospital"]({PUNE_BBOX});

    nwr["amenity"="fire_station"]({PUNE_BBOX});

    nwr["amenity"="police"]({PUNE_BBOX});

    nwr["emergency"="ambulance_station"]({PUNE_BBOX});

    nwr["amenity"="rescue_station"]({PUNE_BBOX});

    nwr["emergency"="water_rescue"]({PUNE_BBOX});

    nwr["emergency"="water_rescue_station"]({PUNE_BBOX});

    nwr["emergency:social_facility"="shelter"]({PUNE_BBOX});

    nwr["amenity"="social_facility"]
       ["social_facility"="shelter"]({PUNE_BBOX});


    /* ==========================================
       PUNE DISTRICT
       ADMIN LEVEL 5
       ========================================== */

    relation
        ["boundary"="administrative"]
        ["admin_level"="5"]
        ["name"="Pune District"];


    /* ==========================================
       TALUKA / SUBDISTRICT
       ADMIN LEVEL 6
       ========================================== */

    relation
        ["boundary"="administrative"]
        ["admin_level"="6"]
        ({PUNE_BBOX});
);

out geom tags;
"""


# ==========================================================
# FETCH DATA FROM OVERPASS API
# ==========================================================

def get_osm_data():

    headers = {
        "User-Agent": "ResQTech-Emergency-GIS/1.0",
        "Accept": "application/json"
    }

    last_error = None

    for server in OVERPASS_SERVERS:

        try:

            print("\n------------------------------------------")
            print("Trying Overpass server:")
            print(server)
            print("------------------------------------------")

            response = requests.get(
                server,
                params={
                    "data": QUERY
                },
                headers=headers,
                timeout=240
            )

            print(
                "HTTP Status:",
                response.status_code
            )

            response.raise_for_status()

            data = response.json()

            elements = data.get(
                "elements",
                []
            )

            print(
                "Objects received:",
                len(elements)
            )

            return elements

        except Exception as error:

            print("\nServer failed:")
            print(error)

            last_error = error

    raise RuntimeError(
        "All Overpass API servers failed.\n"
        f"Last error: {last_error}"
    )


# ==========================================================
# GET COORDINATES
# ==========================================================

def get_coordinates(element):

    # OSM node
    if "lat" in element and "lon" in element:

        return (
            element["lat"],
            element["lon"]
        )

    # OSM way/relation center
    if "center" in element:

        return (
            element["center"]["lat"],
            element["center"]["lon"]
        )

    return None, None


# ==========================================================
# POPUP FOR EMERGENCY FACILITIES
# ==========================================================

def make_popup(tags, facility_type):

    name = tags.get(
        "name",
        "Unnamed Facility"
    )

    phone = tags.get(
        "phone",
        tags.get(
            "contact:phone",
            "Not available"
        )
    )

    address = tags.get(
        "addr:full",
        "Not available"
    )

    website = tags.get(
        "website",
        "Not available"
    )

    html = f"""

    <div style="
        width:270px;
        font-family:Arial;
    ">

        <h4 style="
            margin-bottom:10px;
        ">
            {facility_type}
        </h4>

        <b>Name:</b><br>
        {name}

        <br><br>

        <b>Phone:</b><br>
        {phone}

        <br><br>

        <b>Address:</b><br>
        {address}

        <br><br>

        <b>Website:</b><br>
        {website}

    </div>

    """

    return folium.Popup(
        html,
        max_width=300
    )


# ==========================================================
# TALUKA HIGHLIGHT JAVASCRIPT
# ==========================================================

def add_taluka_highlight_script(m):

    script = """

    <script>

    document.addEventListener(
        "DOMContentLoaded",
        function() {

            var selectedTaluka = null;


            /*
             * Go through every layer
             */
            map.eachLayer(function(layer) {


                /*
                 * Only process Taluka boundaries
                 */
                if (
                    layer instanceof L.Polyline &&
                    layer.options.className ===
                    "taluka-boundary"
                ) {


                    /*
                     * Add click/tap event
                     */
                    layer.on(
                        "click",
                        function() {


                            /*
                             * Restore previous Taluka
                             */
                            if (
                                selectedTaluka &&
                                selectedTaluka !== layer
                            ) {

                                selectedTaluka.setStyle({

                                    color: "#333333",

                                    weight: 2,

                                    opacity: 0.85

                                });

                            }


                            /*
                             * If same Taluka
                             * is clicked again
                             */
                            if (
                                selectedTaluka === layer
                            ) {

                                layer.setStyle({

                                    color: "#333333",

                                    weight: 2,

                                    opacity: 0.85

                                });

                                selectedTaluka = null;

                                return;

                            }


                            /*
                             * Highlight selected Taluka
                             */
                            layer.setStyle({

                                color: "#000000",

                                weight: 6,

                                opacity: 1.0

                            });


                            /*
                             * Bring selected Taluka
                             * to the front
                             */
                            layer.bringToFront();


                            /*
                             * Store selected Taluka
                             */
                            selectedTaluka = layer;

                        }
                    );

                }

            });

        }
    );

    </script>

    """

    m.get_root().html.add_child(
        folium.Element(script)
    )


# ==========================================================
# CREATE MAP
# ==========================================================

def create_map():

    print("\n")
    print("==============================================")
    print("       RESQTECH EMERGENCY GIS MAP")
    print("==============================================")

    print(
        "\nFetching live OpenStreetMap data..."
    )

    elements = get_osm_data()

    print(
        "\nTotal objects received:",
        len(elements)
    )


    # ======================================================
    # BASE MAP
    # ======================================================

    m = folium.Map(

        location=[
            PUNE_LAT,
            PUNE_LON
        ],

        zoom_start=9,

        tiles="OpenStreetMap",

        control_scale=True

    )


    # ======================================================
    # EMERGENCY INFRASTRUCTURE LAYERS
    # ======================================================

    hospital_layer = folium.FeatureGroup(

        name="🏥 Hospitals",

        show=True

    )


    fire_layer = folium.FeatureGroup(

        name="🚒 Fire Stations",

        show=True

    )


    police_layer = folium.FeatureGroup(

        name="👮 Police Stations",

        show=True

    )


    ambulance_layer = folium.FeatureGroup(

        name="🚑 Ambulance Stations",

        show=True

    )


    rescue_layer = folium.FeatureGroup(

        name="🛟 Rescue Stations",

        show=True

    )


    water_layer = folium.FeatureGroup(

        name="🚤 Water Rescue",

        show=True

    )


    shelter_layer = folium.FeatureGroup(

        name="🏠 Emergency Shelters",

        show=True

    )


    # ======================================================
    # ADMINISTRATIVE BOUNDARY LAYERS
    # ======================================================

    district_layer = folium.FeatureGroup(

        name="🟥 Pune District Boundary",

        show=True

    )


    taluka_layer = folium.FeatureGroup(

        name="⬛ Taluka Boundaries",

        show=True

    )


    # ======================================================
    # COUNTERS
    # ======================================================

    hospital_count = 0

    fire_count = 0

    police_count = 0

    ambulance_count = 0

    rescue_count = 0

    water_count = 0

    shelter_count = 0

    taluka_count = 0

    district_count = 0


    # ======================================================
    # PROCESS OSM DATA
    # ======================================================

    for element in elements:

        tags = element.get(
            "tags",
            {}
        )


        # ==================================================
        # ADMINISTRATIVE INFORMATION
        # ==================================================

        boundary = tags.get(
            "boundary",
            ""
        )

        admin_level = tags.get(
            "admin_level",
            ""
        )

        name = tags.get(
            "name",
            "Unnamed"
        )


        # ==================================================
        # PUNE DISTRICT
        # ==================================================

        if (
            boundary == "administrative"
            and admin_level == "5"
            and (
                name == "Pune District"
                or
                name == "पुणे जिल्हा"
            )
        ):

            geometry = element.get(
                "geometry"
            )

            if geometry:

                district_coordinates = [

                    [
                        point["lat"],
                        point["lon"]
                    ]

                    for point in geometry

                ]


                folium.PolyLine(

                    locations=district_coordinates,

                    color="#5A0000",

                    weight=6,

                    opacity=1.0,

                    tooltip="🟥 Pune District Boundary",

                    popup=folium.Popup(

                        """
                        <div style="font-family:Arial;">

                            <h4>
                                Pune District
                            </h4>

                            <b>
                                Administrative Level:
                            </b>

                            District

                        </div>
                        """,

                        max_width=250

                    )

                ).add_to(
                    district_layer
                )


                district_count += 1

            continue


        # ==================================================
        # TALUKA BOUNDARY
        # ==================================================

        if (
            boundary == "administrative"
            and admin_level == "6"
        ):

            geometry = element.get(
                "geometry"
            )

            if geometry:

                taluka_coordinates = [

                    [
                        point["lat"],
                        point["lon"]
                    ]

                    for point in geometry

                ]


                # ------------------------------------------
                # TALUKA BOUNDARY
                # ------------------------------------------

                folium.PolyLine(

                    locations=taluka_coordinates,

                    color="#333333",

                    weight=2,

                    opacity=0.85,

                    tooltip=f"⬛ Taluka: {name}",

                    popup=folium.Popup(

                        f"""

                        <div style="
                            font-family:Arial;
                            width:240px;
                        ">

                            <h4>
                                Taluka / Subdistrict
                            </h4>

                            <b>Name:</b><br>

                            {name}

                            <br><br>

                            <b>
                                Administrative Level:
                            </b>

                            6

                            <br><br>

                            <small>
                            Tap the boundary to
                            highlight this Taluka.
                            </small>

                        </div>

                        """,

                        max_width=280

                    ),

                    class_name="taluka-boundary"

                ).add_to(
                    taluka_layer
                )


                taluka_count += 1

            continue


        # ==================================================
        # COORDINATES FOR AMENITIES
        # ==================================================

        lat, lon = get_coordinates(
            element
        )

        if lat is None or lon is None:
            continue


        # ==================================================
        # TAGS
        # ==================================================

        amenity = tags.get(
            "amenity",
            ""
        )

        emergency = tags.get(
            "emergency",
            ""
        )

        emergency_social = tags.get(
            "emergency:social_facility",
            ""
        )

        social_facility = tags.get(
            "social_facility",
            ""
        )


        # ==================================================
        # HOSPITAL
        # ==================================================

        if amenity == "hospital":

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"🏥 {name}",

                popup=make_popup(
                    tags,
                    "🏥 HOSPITAL"
                ),

                icon=folium.Icon(

                    icon="plus",

                    prefix="fa",

                    color="red"

                )

            ).add_to(
                hospital_layer
            )


            hospital_count += 1


        # ==================================================
        # FIRE STATION
        # ==================================================

        elif amenity == "fire_station":

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"🚒 {name}",

                popup=make_popup(
                    tags,
                    "🚒 FIRE STATION"
                ),

                icon=folium.Icon(

                    icon="fire-extinguisher",

                    prefix="fa",

                    color="red"

                )

            ).add_to(
                fire_layer
            )


            fire_count += 1


        # ==================================================
        # POLICE
        # ==================================================

        elif amenity == "police":

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"👮 {name}",

                popup=make_popup(
                    tags,
                    "👮 POLICE STATION"
                ),

                icon=folium.Icon(

                    icon="shield",

                    prefix="fa",

                    color="blue"

                )

            ).add_to(
                police_layer
            )


            police_count += 1


        # ==================================================
        # AMBULANCE
        # ==================================================

        elif emergency == "ambulance_station":

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"🚑 {name}",

                popup=make_popup(
                    tags,
                    "🚑 AMBULANCE STATION"
                ),

                icon=folium.Icon(

                    icon="ambulance",

                    prefix="fa",

                    color="red"

                )

            ).add_to(
                ambulance_layer
            )


            ambulance_count += 1


        # ==================================================
        # RESCUE STATION
        # ==================================================

        elif amenity == "rescue_station":

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"🛟 {name}",

                popup=make_popup(
                    tags,
                    "🛟 RESCUE STATION"
                ),

                icon=folium.Icon(

                    icon="life-ring",

                    prefix="fa",

                    color="orange"

                )

            ).add_to(
                rescue_layer
            )


            rescue_count += 1


        # ==================================================
        # WATER RESCUE
        # ==================================================

        elif emergency in [

            "water_rescue",

            "water_rescue_station"

        ]:

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"🚤 {name}",

                popup=make_popup(
                    tags,
                    "🚤 WATER RESCUE"
                ),

                icon=folium.Icon(

                    icon="ship",

                    prefix="fa",

                    color="blue"

                )

            ).add_to(
                water_layer
            )


            water_count += 1


        # ==================================================
        # EMERGENCY SHELTER
        # ==================================================

        elif (

            emergency_social == "shelter"

            or

            (
                amenity == "social_facility"
                and
                social_facility == "shelter"
            )

        ):

            folium.Marker(

                location=[
                    lat,
                    lon
                ],

                tooltip=f"🏠 {name}",

                popup=make_popup(
                    tags,
                    "🏠 EMERGENCY SHELTER"
                ),

                icon=folium.Icon(

                    icon="home",

                    prefix="fa",

                    color="green"

                )

            ).add_to(
                shelter_layer
            )


            shelter_count += 1


    # ======================================================
    # ADD EMERGENCY LAYERS TO MAP
    # ======================================================

    hospital_layer.add_to(m)

    fire_layer.add_to(m)

    police_layer.add_to(m)

    ambulance_layer.add_to(m)

    rescue_layer.add_to(m)

    water_layer.add_to(m)

    shelter_layer.add_to(m)


    # ======================================================
    # ADD ADMINISTRATIVE LAYERS
    # ======================================================

    district_layer.add_to(m)

    taluka_layer.add_to(m)


    # ======================================================
    # LAYER CONTROL
    # ======================================================

    folium.LayerControl(

        collapsed=False

    ).add_to(m)


    # ======================================================
    # AMENITIES INFORMATION PANEL
    # ======================================================

    # Keep only the emergency-amenities information panel.
    # Administrative-boundary explanations/legend items are removed.
    amenities_panel = f"""
    <div style="
        position:fixed;
        bottom:25px;
        left:25px;
        width:245px;
        background:white;
        border:2px solid #444;
        border-radius:8px;
        padding:12px 14px;
        z-index:9999;
        font-family:Arial,sans-serif;
        box-shadow:0 2px 8px rgba(0,0,0,0.3);
        line-height:1.55;
    ">
        <h4 style="margin:0 0 8px 0;">
            ResQTech — Emergency Infrastructure
        </h4>

        <div>🏥 Hospitals: <b>{hospital_count}</b></div>
        <div>🚒 Fire Stations: <b>{fire_count}</b></div>
        <div>👮 Police Stations: <b>{police_count}</b></div>
        <div>🚑 Ambulance Stations: <b>{ambulance_count}</b></div>
        <div>🛟 Rescue Stations: <b>{rescue_count}</b></div>
        <div>🚤 Water Rescue: <b>{water_count}</b></div>
        <div>🏠 Emergency Shelters: <b>{shelter_count}</b></div>
    </div>
    """

    m.get_root().html.add_child(
        folium.Element(amenities_panel)
    )


    # ======================================================
    # ADD TALUKA CLICK HIGHLIGHT
    # ======================================================

    add_taluka_highlight_script(
        m
    )


    # ======================================================
    # PRINT SUMMARY
    # ======================================================

    print("\n")
    print("==============================================")
    print("             MAP SUMMARY")
    print("==============================================")

    print(
        "Hospitals:",
        hospital_count
    )

    print(
        "Fire Stations:",
        fire_count
    )

    print(
        "Police Stations:",
        police_count
    )

    print(
        "Ambulance Stations:",
        ambulance_count
    )

    print(
        "Rescue Stations:",
        rescue_count
    )

    print(
        "Water Rescue:",
        water_count
    )

    print(
        "Emergency Shelters:",
        shelter_count
    )

    print(
        "Taluka Boundaries:",
        taluka_count
    )

    print(
        "Pune District Boundary:",
        district_count
    )

    print("==============================================")


    return m


# ==========================================================
# FLASK ROUTE
# ==========================================================

@app.route("/")
def index():

    try:

        map_object = create_map()

        return map_object.get_root().render()


    except Exception as error:

        print("\n")
        print("==============================================")
        print("                 MAP ERROR")
        print("==============================================")

        print(error)

        print("==============================================")
        print("\n")


        return f"""

        <html>

        <head>

            <title>
                ResQTech Map Error
            </title>

        </head>


        <body style="
            font-family:Arial;
            padding:40px;
        ">

            <h2>
                ResQTech Map Error
            </h2>

            <p>
                The map could not be loaded.
            </p>

            <pre style="
                background:#f5f5f5;
                padding:15px;
                border-radius:6px;
            ">
{error}
            </pre>

            <p>
                Check the Git Bash / terminal
                for more details.
            </p>

        </body>

        </html>

        """, 500


# ==========================================================
# START FLASK SERVER
# ==========================================================

if __name__ == "__main__":

    print("\n")

    print("==============================================")
    print("          RESQTECH EMERGENCY GIS")
    print("==============================================")

    print("\nStarting Flask server...")

    print(
        "Map URL: http://127.0.0.1:5000/"
    )

    print(
        "\nFetching OSM data only when map loads."
    )

    print(
        "No OSM files will be downloaded or saved."
    )

    print(
        "\nOpening browser..."
    )


    webbrowser.open(
        "http://127.0.0.1:5000/"
    )


    app.run(

        host="127.0.0.1",

        port=5000,

        debug=False

    )