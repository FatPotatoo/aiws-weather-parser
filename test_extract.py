import unittest

import extract

DEGREE = "\N{DEGREE SIGN}"


class ExtractRegressionTests(unittest.TestCase):
    def extract_sentences(self, *sentences: str) -> list[dict]:
        tracker = extract.EntityTracker("2026-05-01", "sample.docx")
        extract.process_summary_sentences(extract.split_sentences(" ".join(sentences)), tracker)
        return extract.postprocess_entities(tracker.entities)

    def test_less_marked_continuation_removes_previous_entity(self) -> None:
        rows = self.extract_sentences(
            "The trough from southeast Uttar Pradesh to north interior Odisha ran from south Punjab "
            "adjoining northwest Rajasthan to central parts of Madhya Pradesh across East Rajasthan "
            "at 0.9 km above m. s. l.",
            "It became less marked.",
        )

        self.assertEqual([], rows)

    def test_another_wd_and_induced_cycir_are_extracted(self) -> None:
        rows = self.extract_sentences(
            "Another Western Disturbance seen as a trough in middle tropospheric westerlies ran "
            f"roughly along Long. 55{DEGREE}E to the north of Lat. 30{DEGREE}N.",
            "The induced upper air cyclonic circulation over north Punjab & neighbourhood at "
            "1.5 km above m. s. l. persisted.",
        )

        self.assertEqual(["WD", "CYCIR"], [row["weather_system"] for row in rows])
        self.assertEqual(f"along long. 55{DEGREE}e to the north of lat. 30{DEGREE}n", rows[0]["region"])
        self.assertEqual("north punjab & neighbourhood", rows[1]["region"])
        self.assertEqual(1.5, rows[1]["height_km"])

    def test_named_less_marked_update_removes_existing_entity(self) -> None:
        rows = self.extract_sentences(
            "The upper air cyclonic circulation over northeast Assam & neighbourhood persisted "
            "at 1.5 km above m. s. l.",
            "The upper air cyclonic circulation over northeast Assam & neighbourhood became less marked.",
        )

        self.assertEqual([], rows)

    def test_cycir_with_the_trough_aloft_creates_separate_trough(self) -> None:
        rows = self.extract_sentences(
            "An upper air cyclonic circulation lay over southeast Bangladesh and neighbourhood "
            "between 3.1 & 5.8 km above m. s. l. with the trough aloft with its axis at 7.6 km "
            f"above m. s. l. ran roughly along Long. 89{DEGREE}E to the north of Lat. 20{DEGREE}N."
        )

        self.assertEqual(["CYCIR", "Trough"], [row["weather_system"] for row in rows])
        self.assertEqual(7.6, rows[1]["height_km"])
        self.assertIn(f"along long. 89{DEGREE}e", rows[1].get("region_original", rows[1]["region"]))

    def test_fresh_wd_is_split_after_previous_cycir(self) -> None:
        rows = self.extract_sentences(
            "An upper air cyclonic circulation lay over northeast Assam & neighbourhood and extended "
            "upto 1.5 km above m. s. l.",
            "A fresh western disturbance as a trough in middle tropospheric westerlies with its axis "
            f"at 5.8 km above m. s. l. ran roughly along Long. 55{DEGREE}E to the north of Lat. 31{DEGREE}N.",
        )

        self.assertEqual(["CYCIR", "WD"], [row["weather_system"] for row in rows])
        self.assertEqual(5.8, rows[1]["height_km"])

    def test_cycir_keeps_south_coastal_andhra_region(self) -> None:
        rows = self.extract_sentences(
            "The upper air cyclonic circulation over south Coastal Andhra Pradesh & neighbourhood "
            "between 3.1 & 5.8 km above m. s. l. persisted."
        )

        self.assertEqual(["CYCIR"], [row["weather_system"] for row in rows])
        self.assertEqual("south coastal andhra pradesh & neighbourhood", rows[0]["region"])
        self.assertEqual(["Coastal Andhra Pradesh"], extract.map_text_to_form_subdivisions(rows[0]["region"]))


if __name__ == "__main__":
    unittest.main()
