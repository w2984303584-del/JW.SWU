import Course_Selection as course


def test_second_target_matches(monkeypatch):
    monkeypatch.setattr(course, 'TARGETS', ['课程一', '课程二'])
    assert course.CheckName('课程二') is True


def test_empty_targets(monkeypatch):
    monkeypatch.setattr(course, 'TARGETS', [])
    assert course.CheckName('任何课程') is False
