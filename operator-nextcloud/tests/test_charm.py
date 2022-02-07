# Copyright 2020 Erik Lönroth
# See LICENSE file for licensing details.
# import sys
import unittest
from ops.testing import Harness
# from unittest.mock import Mock
# sys.path.append('./src')
import charm


class TestCharm(unittest.TestCase):
    # def test_config_changed(self):
    #     harness = Harness(NextcloudCharm)
    #     # from 0.8 you should also do:
    #     # self.addCleanup(harness.cleanup)
    #     harness.begin()
    #     self.assertEqual(list(harness.charm._stored.things), [])
    #     harness.update_config({"thing": "foo"})
    #     self.assertEqual(list(harness.charm._stored.things), ["foo"])
    #
    # def test_action(self):
    #     harness = Harness(NextcloudCharm)
    #     harness.begin()
    #     # the harness doesn't (yet!) help much with actions themselves
    #     action_event = Mock(params={"fail": ""})
    #     harness.charm._on_fortune_action(action_event)
    #
    #     self.assertTrue(action_event.set_results.called)
    #
    # def test_action_fail(self):
    #     harness = Harness(NextcloudCharm)
    #     harness.begin()
    #     action_event = Mock(params={"fail": "fail this"})
    #     harness.charm._on_fortune_action(action_event)
    #
    #     self.assertEqual(action_event.fail.call_args, [("fail this",)])

    def test_leader_install_hook(self):
        harness = Harness(charm.NextcloudCharm)
        harness.set_leader(True)
        harness.begin()
        harness.charm.on.install.emit()
        # self.assertTrue(harness.charm._stored.nextcloud_fetched)
