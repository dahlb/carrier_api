# Contributing

Everybody is invited and welcome to contribute to this project.

The process is straight-forward.

 - Read [How to get faster PR reviews](https://github.com/kubernetes/community/blob/master/contributors/guide/pull-requests.md#best-practices-for-faster-reviews) by Kubernetes (but skip step 0 and 1)
 - Fork the [git repository](https://github.com/dahlb/carrier_api).
   - Add a new method try to keep its signature as similar to other region/brands as possible.
   - Add example responses
     - modify a stub file
     - run `./.venv/bin/python src/carrier_api/stub.py` (`.\.venv\Scripts\python src/carrier_api/stub.py` on Windows)
     - add the logging from the console to the source code
 - Create a Pull Request against the [**main**](https://github.com/dahlb/carrier_api/tree/main) branch.

## Issues (Features/Bugs)

If you want to suggest a new feature or found a problem using the API, please open a ticket in [Issues](https://github.com/dahlb/ha_carrier/issues).
