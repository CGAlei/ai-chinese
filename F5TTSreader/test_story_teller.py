#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for story_teller.py helper functions.
"""

import unittest
from story_teller import normalize_text, split_into_chunks, num_to_chinese

class TestStoryTeller(unittest.TestCase):

    def test_num_to_chinese(self):
        self.assertEqual(num_to_chinese(0), "零")
        self.assertEqual(num_to_chinese(10), "十")
        self.assertEqual(num_to_chinese(11), "十一")
        self.assertEqual(num_to_chinese(20), "二十")
        self.assertEqual(num_to_chinese(100), "一百")
        self.assertEqual(num_to_chinese(105), "一百零五")
        self.assertEqual(num_to_chinese(1000), "一千")
        self.assertEqual(num_to_chinese(1001), "一千零一")
        self.assertEqual(num_to_chinese(12345), "一万二千三百四十五")
        self.assertEqual(num_to_chinese(10001), "一万零一")
        self.assertEqual(num_to_chinese(100000), "十万")
        self.assertEqual(num_to_chinese(1000000), "一百万")

    def test_normalize_text(self):
        # Test Year conversions
        self.assertEqual(normalize_text("2026"), "二零二六年")
        self.assertEqual(normalize_text("2026年"), "二零二六年")
        self.assertEqual(normalize_text("1998年"), "一九九八年")
        
        # Test Percentage conversions
        self.assertEqual(normalize_text("25%"), "百分之二十五")
        self.assertEqual(normalize_text("3.5%"), "百分之三点五")
        
        # Test Decimal conversions
        self.assertEqual(normalize_text("3.5"), "三点五")
        self.assertEqual(normalize_text("123.45"), "一百二十三点四五")
        
        # Test General numbers
        self.assertEqual(normalize_text("我有10个苹果"), "我有十个苹果")
        
        # Test Edge characters stripping
        self.assertEqual(normalize_text("你好#世界! @2026*"), "你好世界! 二零二六年")
        
        # Test Code-switching preservation (secondary languages)
        self.assertEqual(normalize_text("这是 Spanish: Hola amigo."), "这是 Spanish: Hola amigo.")

    def test_split_into_chunks(self):
        # Simple short text
        text = "这是一个简单的句子。"
        chunks = split_into_chunks(text, max_chars=50)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)
        
        # Multiple clauses
        text = "欢迎大家来到中文故事会，今天我们要讲一个非常有趣的故事。主人公是小兔子，它非常聪明。"
        chunks = split_into_chunks(text, max_chars=50)
        # Check that no chunk exceeds 50 characters
        for c in chunks:
            self.assertTrue(len(c) <= 50, f"Chunk too long: {c}")
            
        # Verify long clause splits
        long_clause = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长且没有任何标点符号的句子。"
        chunks = split_into_chunks(long_clause, max_chars=10)
        for c in chunks:
            self.assertTrue(len(c) <= 10, f"Chunk too long: {c}")

if __name__ == "__main__":
    unittest.main()
