pre-commit: format check test

test:
	coverage run -m unittest
	coverage report

format:
	black oysterpack
	black tests

# enforces style guide
check:
	flake8 oysterpack
	flake8 tests
	mypy oysterpack
	mypy tests