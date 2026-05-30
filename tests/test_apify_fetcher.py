from src.apify_fetcher import _get_run_value


class FakeRun:
    default_dataset_id = "dataset-from-attribute"


class FakePydanticRun:
    def model_dump(self, by_alias=False):
        if by_alias:
            return {"defaultDatasetId": "dataset-from-alias"}
        return {"default_dataset_id": "dataset-from-snake"}


def test_get_run_value_supports_dict_run_response():
    assert _get_run_value({"defaultDatasetId": "dataset-from-dict"}, "defaultDatasetId") == "dataset-from-dict"


def test_get_run_value_supports_pydantic_run_response():
    assert _get_run_value(FakePydanticRun(), "defaultDatasetId") == "dataset-from-alias"


def test_get_run_value_supports_object_attribute_response():
    assert _get_run_value(FakeRun(), "defaultDatasetId") == "dataset-from-attribute"
