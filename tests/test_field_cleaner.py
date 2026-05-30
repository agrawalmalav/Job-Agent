from src.field_cleaner import clean_apify_job


def test_field_mapping_from_apify_columns():
    raw = {
        "applicantsCount": 42,
        "applyMethod": "Easy Apply",
        "applyUrl": "https://apply.example/job",
        "companyLinkedinUrl": "https://linkedin.com/company/example",
        "companyName": "Example Ltd",
        "country": "United Kingdom",
        "descriptionText": "Python role",
        "employmentType": "Full-time",
        "expireAt": "2026-06-01",
        "id": "apify-123",
        "industries": ["Software Development"],
        "jobFunction": "Engineering",
        "link": "https://linkedin.com/jobs/view/123",
        "location": "London",
        "postedAt": "1 day ago",
        "postedAtTimestamp": "2026-05-23T10:00:00Z",
        "salary": "GBP 50000",
        "salaryInsights": {
            "compensationBreakdown": [
                {
                    "currencyCode": "GBP",
                    "maxSalary": 70000,
                    "minSalary": 50000,
                    "payPeriod": "YEARLY",
                }
            ]
        },
        "seniorityLevel": "Entry level",
        "standardizedTitle": "Software Engineer",
        "title": "Junior Software Engineer",
        "workRemoteAllowed": True,
        "workplaceTypes": ["Hybrid"],
        "companyLogo": "ignored",
    }

    job = clean_apify_job(raw)

    assert job.apify_id == "apify-123"
    assert job.company_name == "Example Ltd"
    assert job.linkedin_url == "https://linkedin.com/jobs/view/123"
    assert job.currency_code == "GBP"
    assert job.min_salary == "50000"
    assert job.max_salary == "70000"
    assert job.pay_period == "YEARLY"
    assert job.workplace_type == "Hybrid"
    assert job.industries == '["Software Development"]'
    assert job.raw is raw
