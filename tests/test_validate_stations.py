import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from validate_stations import check_files, check_station, load_files, notices  # noqa: E402

FIXED = {
    "id": "SN99895",
    "name": "Test station",
    "project": "Test",
    "variables": {"airTemperature": "temperature"},
    "icon": "weather-station",
    "lat": 78.2,
    "lon": 15.6,
    "url": "https://example.org/station",
}
MOBILE = {
    "id": "boat",
    "name": "Test boat",
    "project": "Test",
    "variables": {"airTemperature": "temperature"},
    "icon": "boat",
    "url": "https://example.org/boat",
    "import_function": "netcdf_boat.netcdf_boat",
}
KNOWN = {"FrostSource", "HolfuySource"}


def fixed(**changes):
    station = copy.deepcopy(FIXED)
    station.update(changes)
    return station


class StructureTest(unittest.TestCase):
    def test_valid_fixed_and_mobile_stations_pass(self):
        self.assertEqual(check_station(FIXED, "fixed"), [])
        self.assertEqual(check_station(MOBILE, "mobile"), [])

    def test_a_missing_required_field_is_reported(self):
        for field in ("id", "name", "project", "icon", "variables", "lat", "lon"):
            station = fixed()
            del station[field]
            self.assertTrue(check_station(station, "fixed"), field)

    def test_coordinates_out_of_range_or_not_numbers(self):
        self.assertTrue(check_station(fixed(lat=91), "fixed"))
        self.assertTrue(check_station(fixed(lon=-181), "fixed"))
        self.assertTrue(check_station(fixed(lat="78.2"), "fixed"))
        self.assertTrue(check_station(fixed(lat=True), "fixed"))

    def test_a_mobile_station_needs_no_position_but_a_given_one_is_checked(self):
        self.assertEqual(check_station(MOBILE, "mobile"), [])
        self.assertTrue(check_station({**MOBILE, "lat": 120.0, "lon": 15.0}, "mobile"))

    def test_the_mobile_import_function_must_look_like_module_dot_function(self):
        self.assertTrue(check_station({**MOBILE, "import_function": "netcdf_boat"}, "mobile"))
        self.assertTrue(check_station({k: v for k, v in MOBILE.items() if k != "import_function"}, "mobile"))

    def test_variables_must_be_an_object_of_strings_or_null(self):
        self.assertTrue(check_station(fixed(variables=["airTemperature"]), "fixed"))
        self.assertTrue(check_station(fixed(variables={"airTemperature": ""}), "fixed"))
        self.assertTrue(check_station(fixed(variables={"": "temperature"}), "fixed"))
        self.assertTrue(check_station(fixed(variables={"airTemperature": 3}), "fixed"))

    def test_an_empty_variables_object_and_null_values_are_allowed(self):
        self.assertEqual(check_station(fixed(variables={}), "fixed"), [])
        self.assertEqual(check_station(fixed(variables={"seaSurfaceTemperature": None}), "fixed"), [])

    def test_the_url_must_be_https(self):
        self.assertTrue(check_station(fixed(url="http://example.org"), "fixed"))
        self.assertTrue(check_station(fixed(url=""), "fixed"))

    def test_the_id_must_use_safe_characters(self):
        self.assertTrue(check_station(fixed(id="a b"), "fixed"))
        self.assertTrue(check_station(fixed(id="../x"), "fixed"))
        self.assertTrue(check_station(fixed(id=""), "fixed"))

    def test_a_station_that_is_not_an_object(self):
        self.assertEqual(check_station("SN1", "fixed"), ["is not an object"])


class DatasourceTest(unittest.TestCase):
    def test_a_known_datasource_passes_and_none_is_allowed(self):
        self.assertEqual(check_station(fixed(datasource="HolfuySource"), "fixed", KNOWN), [])
        self.assertEqual(check_station(fixed(), "fixed", KNOWN), [])

    def test_a_typo_would_fall_back_silently_so_it_is_an_error(self):
        problems = check_station(fixed(datasource="HolfuySourc"), "fixed", KNOWN)
        self.assertEqual(len(problems), 1)
        self.assertIn("silently fall back", problems[0])

    def test_names_are_not_checked_without_a_list(self):
        self.assertEqual(check_station(fixed(datasource="Anything"), "fixed"), [])


class FilesTest(unittest.TestCase):
    def test_ids_must_be_unique_across_both_files(self):
        errors = check_files({"fixed": [FIXED], "mobile": [{**MOBILE, "id": FIXED["id"]}]})
        self.assertEqual(len(errors), 1)
        self.assertIn("also used in fixed_stations.json", errors[0])

    def test_an_empty_or_non_list_file_is_an_error(self):
        self.assertTrue(check_files({"fixed": [], "mobile": [MOBILE]}))
        self.assertTrue(check_files({"fixed": {"id": "x"}, "mobile": [MOBILE]}))

    def test_errors_name_the_file_and_station(self):
        errors = check_files({"fixed": [fixed(lat=99)], "mobile": [MOBILE]})
        self.assertTrue(errors[0].startswith("fixed_stations.json [SN99895]:"))

    def test_stations_without_variables_are_reported_as_notes_not_errors(self):
        contents = {"fixed": [fixed(id="SN1", variables={}), FIXED], "mobile": [MOBILE]}
        self.assertEqual(check_files(contents), [])
        self.assertEqual(len(notices(contents)), 1)
        self.assertIn("SN1", notices(contents)[0])

    def test_the_committed_station_files_are_valid(self):
        contents, load_errors = load_files(ROOT / "stations")
        self.assertEqual(load_errors, [])
        self.assertEqual(check_files(contents), [])


if __name__ == "__main__":
    unittest.main()
