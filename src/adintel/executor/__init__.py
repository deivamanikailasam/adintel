"""The Action Executor — deliberately *not* an agent.

It is the only component with ad-platform **write** credentials, and it has **no model access at all**
(``tests/unit/test_executor.py::test_executor_cannot_import_any_model_code`` enforces this). Keeping
money-moving code free of any model means no prompt can ever turn into a spend.
"""
