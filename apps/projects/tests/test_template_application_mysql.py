from . import test_template_application as cases
from . import test_task_detail_mysql as fixtures


class TemplateApplicationMySQLTests(cases.TemplateApplicationTests):
    setUpClass = classmethod(fixtures.TaskDetailMySQLTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.TaskDetailMySQLTests.tearDownClass.__func__)
    setUp = fixtures.TaskDetailMySQLTests.setUp
    tearDown = fixtures.TaskDetailMySQLTests.tearDown
