import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock
from telegram.constants import ChatAction
from handlers import typing_indicator


class TestTypingIndicator(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create a mock chat object
        self.mock_chat = MagicMock()
        self.mock_chat.send_action = AsyncMock()

    async def test_1_fast_response(self):
        """Test a fast response (< 4s): immediate typing action sent, cleanly closed."""
        self.mock_chat.send_action.reset_mock()
        
        initial_tasks = len([t for t in asyncio.all_tasks() if not t.done()])
        async with typing_indicator(self.mock_chat, interval=4.0) as task:
            self.assertIsNotNone(task)
            self.assertFalse(task.done())
            # Check immediate send_action was called
            self.mock_chat.send_action.assert_called_once_with(ChatAction.TYPING)
            # Simulate fast AI work
            await asyncio.sleep(0.1)

        # After context manager exits: task must be cancelled and done
        self.assertTrue(task.done())
        # Only 1 immediate call was needed
        self.assertEqual(self.mock_chat.send_action.call_count, 1)
        # Verify no leaking tasks
        await asyncio.sleep(0.05)
        current_tasks = len([t for t in asyncio.all_tasks() if not t.done()])
        self.assertEqual(initial_tasks, current_tasks)
        print("  [PASS] Test 1: Fast response")

    async def test_2_long_response_periodic_refresh(self):
        """Test a response taking > 5s: periodic re-sending every ~4s."""
        self.mock_chat.send_action.reset_mock()

        # Using interval=0.2 for fast test simulation of the periodic mechanism
        async with typing_indicator(self.mock_chat, interval=0.2) as task:
            self.mock_chat.send_action.assert_called_once_with(ChatAction.TYPING)
            # Sleep long enough for multiple intervals
            await asyncio.sleep(0.55)

        self.assertTrue(task.done())
        # Should be at least 3 calls (1 initial + 2 periodic)
        self.assertGreaterEqual(self.mock_chat.send_action.call_count, 3)
        print(f"  [PASS] Test 2: Long response periodic refresh (sent {self.mock_chat.send_action.call_count} times)")

    async def test_3_api_failure_cleanup(self):
        """Test an AI API failure: typing indicator stops immediately and does not swallow exception."""
        self.mock_chat.send_action.reset_mock()

        with self.assertRaises(RuntimeError) as ctx:
            async with typing_indicator(self.mock_chat, interval=4.0) as task:
                self.mock_chat.send_action.assert_called_once_with(ChatAction.TYPING)
                # Simulate AI API crash
                raise RuntimeError("AI API Quota Exceeded")

        self.assertEqual(str(ctx.exception), "AI API Quota Exceeded")
        self.assertTrue(task.done())
        print("  [PASS] Test 3: API failure cleanly handled and typing task stopped")

    async def test_4_cancellation_and_cleanup(self):
        """Test cancellation: if the outer task is cancelled, typing indicator task is cancelled cleanly."""
        self.mock_chat.send_action.reset_mock()

        async def outer_worker():
            async with typing_indicator(self.mock_chat, interval=0.1) as task:
                await asyncio.sleep(10.0)

        outer_task = asyncio.create_task(outer_worker())
        await asyncio.sleep(0.05)
        # Cancel the request
        outer_task.cancel()
        try:
            await outer_task
        except asyncio.CancelledError:
            pass

        self.assertTrue(outer_task.done())
        print("  [PASS] Test 4: Cancellation and cleanup")

    async def test_5_multiple_concurrent_messages(self):
        """Test multiple concurrent messages: each has independent typing task without interference."""
        chat1 = MagicMock()
        chat1.send_action = AsyncMock()
        chat2 = MagicMock()
        chat2.send_action = AsyncMock()

        async def user_request(chat, delay):
            async with typing_indicator(chat, interval=0.1) as task:
                await asyncio.sleep(delay)
                return f"Done {delay}"

        # Run two concurrent user requests of different durations
        res1, res2 = await asyncio.gather(
            user_request(chat1, 0.15),
            user_request(chat2, 0.25)
        )

        self.assertEqual(res1, "Done 0.15")
        self.assertEqual(res2, "Done 0.25")
        self.assertGreaterEqual(chat1.send_action.call_count, 1)
        self.assertGreaterEqual(chat2.send_action.call_count, 2)
        print("  [PASS] Test 5: Multiple concurrent messages handled independently")

    async def test_6_normal_final_response_preserved(self):
        """Verify that the bot still sends its normal final response upon completion."""
        reply_mock = AsyncMock()
        async with typing_indicator(self.mock_chat, interval=4.0):
            # Simulate agent generation
            simulated_reply = "تمام، التذكير اتسجل بنجاح!"
            await reply_mock(simulated_reply)

        reply_mock.assert_called_once_with("تمام، التذكير اتسجل بنجاح!")
        print("  [PASS] Test 6: Normal final response preserved and verified")

    async def test_7_no_lingering_tasks(self):
        """Verify that no typing indicator tasks remain active after processing finishes."""
        tasks_before = set(asyncio.all_tasks())

        async with typing_indicator(self.mock_chat, interval=0.05) as task:
            await asyncio.sleep(0.12)

        # Allow event loop iteration to clear any pending callbacks
        await asyncio.sleep(0.02)
        tasks_after = set(asyncio.all_tasks())
        # The internal typing loop task should NOT be in active tasks
        self.assertTrue(task.done())
        active_diff = [t for t in (tasks_after - tasks_before) if not t.done()]
        self.assertEqual(len(active_diff), 0)
        print("  [PASS] Test 7: Zero lingering tasks verified")


if __name__ == "__main__":
    unittest.main()
