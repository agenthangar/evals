from bench.patches import affected_paths, is_test_path, split_by_paths

SAMPLE = """\
diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-old
+new
diff --git a/tests/test_app.py b/tests/test_app.py
new file mode 100644
index 000..333
--- /dev/null
+++ b/tests/test_app.py
@@ -0,0 +1 @@
+assert True
"""


def test_affected_paths():
    assert affected_paths(SAMPLE) == {"src/app.py", "tests/test_app.py"}


def test_split_by_paths():
    tests, source = split_by_paths(SAMPLE, is_test_path)
    assert "tests/test_app.py" in tests and "src/app.py" not in tests
    assert "src/app.py" in source and "tests/test_app.py" not in source
    # Nothing lost in the split
    assert sorted((tests + source).splitlines()) == sorted(SAMPLE.splitlines())


def test_split_empty():
    assert split_by_paths("", is_test_path) == ("", "")


def test_is_test_path():
    positives = [
        "tests/test_app.py",
        "test/foo.js",
        "src/__tests__/bar.tsx",
        "pkg/thing_test.go",
        "src/app.test.ts",
        "src/app.spec.js",
        "conftest.py",
        "spec/models/user_spec.rb",
        "test_utils.py",
        "SampleEngine/Tests/SampleEngineTests/StateTests.swift",
        "SampleAppUITests/FirstRunTests.swift",
        "ios/SampleClientTests/APIClientTests.swift",
        "src/WidgetTests.swift",
    ]
    negatives = ["src/app.py", "README.md", "testimonials/page.tsx", "contest.py", "protest/x.py"]
    for p in positives:
        assert is_test_path(p), p
    for p in negatives:
        assert not is_test_path(p), p
