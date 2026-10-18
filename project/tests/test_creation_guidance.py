"""Discovery and read-only delivery of bundled creation methods."""
import json
import unittest
from unittest.mock import patch, Mock

from pixel_workbench.creation_guidance import TOPICS, workflow_entry, workflow_help, workflow_resource
from pixel_workbench.guidance import onboarding
from pixel_workbench import mcp_server


class CreationGuidanceTests(unittest.TestCase):
    def test_onboarding_has_bounded_machine_readable_entry_and_preserves_state(self):
        state = {"name": "untouched", "revision": 17}
        result = onboarding(state)
        entry = result["creation_workflow"]
        self.assertEqual(entry["read_next"], {"tool": "pixel_help", "arguments": {"topic": "workflow"}})
        self.assertEqual(entry['single_image_animation']['read_next'],
                         {'tool':'pixel_help','arguments':{'topic':'decomposition_workflow'}})
        self.assertLess(len(json.dumps(entry)), 4000)
        self.assertEqual(state, {"name": "untouched", "revision": 17})
        self.assertEqual(result["current_document"], state)
        entry["stages"].clear()
        self.assertTrue(workflow_entry()["stages"])

    def test_all_methods_are_readable_without_starting_or_editing_an_editor(self):
        with patch.object(mcp_server, "ensure_editor", side_effect=AssertionError("Must not start editor")):
            for topic in TOPICS:
                response = mcp_server.pixel_help(topic=topic)
                self.assertFalse(response.isError)
                content = response.structuredContent
                self.assertEqual(content["topic"], topic)
                self.assertGreater(len(content["guide"]), 1500)
                for related in content["related"]:
                    self.assertIn(related["arguments"]["topic"], TOPICS)
                self.assertLessEqual(len(content['related']), 4)
            resource = json.loads(mcp_server.creation_workflow_resource())
        self.assertEqual(set(resource), set(TOPICS))

    def test_operation_help_and_existing_categories_remain_available(self):
        result = mcp_server.pixel_help(topic="workflow", operation="polygon").structuredContent
        self.assertEqual(result["operation"], "polygon")
        self.assertEqual(mcp_server.pixel_help(topic="animation").structuredContent["topic"], "animation")
        overview = mcp_server.pixel_help().structuredContent
        self.assertTrue(set(TOPICS) <= set(overview["topics"]))

    def test_methods_cover_clean_cels_real_evidence_and_host_capabilities(self):
        guides = workflow_resource()
        self.assertIn("does not provide arbitrary script execution", guides["workflow"]["guide"])
        animation = guides["animation_workflow"]["guide"]
        self.assertIn("blank=true", animation)
        self.assertIn("clear ONLY the moving layer", animation)
        inspection = guides["inspection_workflow"]["guide"]
        self.assertIn("ALL evidence pages", inspection)
        self.assertIn('method="frames_and_timing"', inspection)
        self.assertIn("Never mechanically fill", inspection)
        decomposition = guides['decomposition_workflow']['guide']
        self.assertIn('pixel_preview(frame=..., layers=[observed_layer_id]', decomposition)
        self.assertIn('DOES NOT prove', decomposition)
        self.assertIn('Trial the connections', decomposition)
        self.assertIn('Conversion-only', decomposition)
        self.assertIn("not finished", workflow_entry()["scope"])

    def test_existing_prompts_direct_clients_to_methods_without_authorizing_redraw(self):
        self.assertIn("topic='workflow'", mcp_server.draw_sprite_prompt("test"))
        self.assertIn("topic='animation_workflow'", mcp_server.animate_sprite_prompt("test"))
        self.assertIn("topic='decomposition_workflow'", mcp_server.animate_sprite_prompt("test"))
        self.assertIn("topic='inspection_workflow'", mcp_server.finish_and_review_prompt())
        self.assertIn("explicit request", mcp_server.redraw_reference_prompt())

    def test_old_backend_cannot_silently_return_composite_as_isolated_part(self):
        client = Mock()
        client.request.return_value = {'document_id':'old','revision':1,'preview_png':'unused'}
        with patch.object(mcp_server,'ensure_editor',return_value=client):
            response=mcp_server.pixel_preview(layers=['part'])
        self.assertTrue(response.isError)
        self.assertEqual(response.structuredContent['code'],'BACKEND_UPGRADE_REQUIRED')
        self.assertFalse(any(item.type=='image' for item in response.content))


if __name__ == "__main__":
    unittest.main()
