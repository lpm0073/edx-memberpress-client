build:
	# -------------------------------------------------------------------------
	# build package and upload to PyPi.
	# https://pypi.org/project/edx-memberpress-client/
	# -------------------------------------------------------------------------
	python3 -m pip install --upgrade setuptools wheel twine
	python -m pip install --upgrade build

	if [ -d "./build" ]; then sudo rm -r build; fi
	if [ -d "./dist" ]; then sudo rm -r dist; fi
	if [ -d "./edx_memberpress_client.egg-info" ]; then sudo rm -r edx_memberpress_client.egg-info; fi

	python3 -m build --sdist ./
	python3 -m build --wheel ./

	python3 -m pip install --upgrade twine
	twine check dist/*

release-test:
	make build
	twine upload --skip-existing --repository testpypi dist/*


release-prod:
	make build
	twine upload --skip-existing dist/*
