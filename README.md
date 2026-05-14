# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                              |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|-------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/carrier\_api/\_\_init\_\_.py                  |       11 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/api\_connection\_graphql.py      |      164 |      122 |       44 |        0 |     20% |46-51, 55, 64-106, 110-113, 121-134, 149-159, 169-224, 235-378, 391-448, 458-467, 478-495, 507-524, 535-552, 567-570, 589-596, 613-616, 641-662, 682-694, 718-729, 741-750, 776-789 |
| src/carrier\_api/api\_websocket.py                |       80 |       53 |       26 |        0 |     25% |57, 65-81, 85, 96-116, 124-134, 138, 142-146 |
| src/carrier\_api/api\_websocket\_data\_updater.py |       67 |        9 |       26 |        3 |     85% |89, 113-118, 122-123 |
| src/carrier\_api/config.py                        |      120 |       34 |       30 |        4 |     65% |50, 64, 72, 111-114, 153, 157-159, 165, 176-187, 196-209, 217, 225, 261-\>263, 280, 293, 301 |
| src/carrier\_api/const.py                         |       27 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/energy.py                        |       58 |       10 |        6 |        0 |     78% |37, 55, 63, 128-131, 139, 159, 167 |
| src/carrier\_api/errors.py                        |        3 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/live\_smoke\_test.py             |       95 |       95 |       20 |        0 |      0% |    26-211 |
| src/carrier\_api/profile.py                       |       35 |        3 |        0 |        0 |     91% |54, 75, 83 |
| src/carrier\_api/status.py                        |       87 |       20 |       16 |        1 |     70% |48-55, 63, 84, 92, 129-\>131, 154-159, 167, 193, 201 |
| src/carrier\_api/system.py                        |       19 |        3 |        0 |        0 |     84% |43, 58, 66 |
| src/carrier\_api/util.py                          |       27 |        3 |        8 |        1 |     89% |33-\>32, 51-53 |
| **TOTAL**                                         |  **793** |  **352** |  **176** |    **9** | **50%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/dahlb/carrier_api/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dahlb/carrier_api/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fdahlb%2Fcarrier_api%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.