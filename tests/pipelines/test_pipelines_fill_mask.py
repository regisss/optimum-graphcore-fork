# Copyright 2020 The HuggingFace Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

from transformers import MODEL_FOR_MASKED_LM_MAPPING
from transformers.pipelines import PipelineException
from transformers.testing_utils import nested_simplify, require_torch, slow

from optimum.graphcore import pipeline

from .test_pipelines_common import ANY, PipelineTestCaseMeta


class FillMaskPipelineTests(unittest.TestCase, metaclass=PipelineTestCaseMeta):
    model_mapping = MODEL_FOR_MASKED_LM_MAPPING

    @require_torch
    def test_small_model_pt(self):
        unmasker = pipeline(
            task="fill-mask",
            model="sshleifer/tiny-distilroberta-base",
            ipu_config={"layers_per_ipu": [2], "ipus_per_replica": 1},
            top_k=2,
            framework="pt",
        )

        outputs = unmasker("My name is <mask>")
        self.assertEqual(
            nested_simplify(outputs, decimals=6),
            [
                {"sequence": "My name is Maul", "score": 2.2e-05, "token": 35676, "token_str": " Maul"},
                {"sequence": "My name isELS", "score": 2.2e-05, "token": 16416, "token_str": "ELS"},
            ],
        )

        outputs = unmasker("The largest city in France is <mask>")
        self.assertEqual(
            nested_simplify(outputs, decimals=6),
            [
                {
                    "sequence": "The largest city in France is Maul",
                    "score": 2.2e-05,
                    "token": 35676,
                    "token_str": " Maul",
                },
                {"sequence": "The largest city in France isELS", "score": 2.2e-05, "token": 16416, "token_str": "ELS"},
            ],
        )

        outputs = unmasker("My name is <mask>", targets=[" Patrick", " Clara", " Teven"], top_k=3)
        self.assertEqual(
            nested_simplify(outputs, decimals=6),
            [
                {"sequence": "My name is Patrick", "score": 2.1e-05, "token": 3499, "token_str": " Patrick"},
                {"sequence": "My name is Te", "score": 2e-05, "token": 2941, "token_str": " Te"},
                {"sequence": "My name is Clara", "score": 2e-05, "token": 13606, "token_str": " Clara"},
            ],
        )

        outputs = unmasker("My name is <mask> <mask>", top_k=2)

        self.assertEqual(
            nested_simplify(outputs, decimals=6),
            [
                [
                    {
                        "score": 2.2e-05,
                        "token": 35676,
                        "token_str": " Maul",
                        "sequence": "<s>My name is Maul<mask></s>",
                    },
                    {"score": 2.2e-05, "token": 16416, "token_str": "ELS", "sequence": "<s>My name isELS<mask></s>"},
                ],
                [
                    {
                        "score": 2.2e-05,
                        "token": 35676,
                        "token_str": " Maul",
                        "sequence": "<s>My name is<mask> Maul</s>",
                    },
                    {"score": 2.2e-05, "token": 16416, "token_str": "ELS", "sequence": "<s>My name is<mask>ELS</s>"},
                ],
            ],
        )

    @slow
    @require_torch
    def test_large_model_pt(self):
        unmasker = pipeline(
            task="fill-mask",
            model="distilroberta-base",
            ipu_config={"layers_per_ipu": [6], "ipus_per_replica": 1},
            top_k=2,
            framework="pt",
            fp16=False,
        )
        self.run_large_test(unmasker)

    def run_large_test(self, unmasker):
        outputs = unmasker("My name is <mask>")
        self.assertEqual(
            nested_simplify(outputs),
            [
                {"sequence": "My name is John", "score": 0.008, "token": 610, "token_str": " John"},
                {"sequence": "My name is Chris", "score": 0.007, "token": 1573, "token_str": " Chris"},
            ],
        )
        outputs = unmasker("The largest city in France is <mask>")
        self.assertEqual(
            nested_simplify(outputs),
            [
                {
                    "sequence": "The largest city in France is Paris",
                    "score": 0.251,
                    "token": 2201,
                    "token_str": " Paris",
                },
                {
                    "sequence": "The largest city in France is Lyon",
                    "score": 0.215,  # changed from upstream value of 0.214
                    "token": 12790,
                    "token_str": " Lyon",
                },
            ],
        )

        outputs = unmasker("My name is <mask>", targets=[" Patrick", " Clara", " Teven"], top_k=3)
        self.assertEqual(
            nested_simplify(outputs),
            [
                {"sequence": "My name is Patrick", "score": 0.005, "token": 3499, "token_str": " Patrick"},
                {"sequence": "My name is Clara", "score": 0.000, "token": 13606, "token_str": " Clara"},
                {"sequence": "My name is Te", "score": 0.000, "token": 2941, "token_str": " Te"},
            ],
        )

    # @require_torch
    # def test_model_no_pad_pt(self):
    #     unmasker = pipeline(
    #         task="fill-mask",
    #         model="sshleifer/tiny-distilroberta-base",
    #         ipu_config="Graphcore/roberta-base-ipu",
    #         framework="pt",
    #     )
    #     unmasker.tokenizer.pad_token_id = None
    #     unmasker.tokenizer.pad_token = None
    #     self.run_pipeline_test(unmasker, [])

    def get_test_pipeline(self, model, ipu_config, tokenizer, feature_extractor):
        if tokenizer is None or tokenizer.mask_token_id is None:
            self.skipTest("The provided tokenizer has no mask token, (probably reformer or wav2vec2)")

        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            ipu_config=ipu_config,
            tokenizer=tokenizer,
        )
        examples = [f"This is a {tokenizer.mask_token} test"]
        return fill_masker, examples

    def run_pipeline_test(self, fill_masker, examples):
        tokenizer = fill_masker.tokenizer
        model = fill_masker.model

        outputs = fill_masker(examples[0])
        self.assertEqual(
            outputs,
            [
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
            ],
        )

        outputs = fill_masker(examples)
        self.assertEqual(
            outputs,
            [
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
            ],
        )

        outputs = fill_masker(examples * 2)
        self.assertEqual(
            outputs,
            [
                [
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                ],
                [
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                ],
            ],
        )

        with self.assertRaises(ValueError):
            fill_masker([None])
        # No mask_token is not supported
        with self.assertRaises(PipelineException):
            fill_masker("This is")

        self.run_test_top_k(model, tokenizer)
        self.run_test_targets(model, tokenizer)
        self.run_test_top_k_targets(model, tokenizer)
        self.fill_mask_with_duplicate_targets_and_top_k(model, tokenizer)
        self.fill_mask_with_multiple_masks(model, tokenizer)

    def run_test_targets(self, model, tokenizer):
        vocab = tokenizer.get_vocab()
        targets = sorted(vocab.keys())[:2]
        # Pipeline argument
        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
            targets=targets,
        )
        outputs = fill_masker(f"This is a {tokenizer.mask_token}")
        self.assertEqual(
            outputs,
            [
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
            ],
        )
        target_ids = {vocab[el] for el in targets}
        self.assertEqual({el["token"] for el in outputs}, target_ids)
        self.assertEqual({el["token_str"] for el in outputs}, set(targets))

        # Call argument
        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
        )
        outputs = fill_masker(f"This is a {tokenizer.mask_token}", targets=targets)
        self.assertEqual(
            outputs,
            [
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
            ],
        )
        target_ids = {vocab[el] for el in targets}
        self.assertEqual({el["token"] for el in outputs}, target_ids)
        self.assertEqual({el["token_str"] for el in outputs}, set(targets))

        # Score equivalence
        outputs = fill_masker(f"This is a {tokenizer.mask_token}", targets=targets)
        tokens = [top_mask["token_str"] for top_mask in outputs]
        scores = [top_mask["score"] for top_mask in outputs]

        unmasked_targets = fill_masker(f"This is a {tokenizer.mask_token}", targets=tokens)
        target_scores = [top_mask["score"] for top_mask in unmasked_targets]
        self.assertEqual(nested_simplify(scores), nested_simplify(target_scores))

        # Raises with invalid
        with self.assertRaises(ValueError):
            outputs = fill_masker(f"This is a {tokenizer.mask_token}", targets=[""])
        with self.assertRaises(ValueError):
            outputs = fill_masker(f"This is a {tokenizer.mask_token}", targets=[])
        with self.assertRaises(ValueError):
            outputs = fill_masker(f"This is a {tokenizer.mask_token}", targets="")

    def run_test_top_k(self, model, tokenizer):
        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
            top_k=2,
        )
        outputs = fill_masker(f"This is a {tokenizer.mask_token}")
        self.assertEqual(
            outputs,
            [
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
            ],
        )

        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
        )
        outputs2 = fill_masker(f"This is a {tokenizer.mask_token}", top_k=2)
        self.assertEqual(
            outputs2,
            [
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
            ],
        )
        self.assertEqual(nested_simplify(outputs), nested_simplify(outputs2))

    def run_test_top_k_targets(self, model, tokenizer):
        vocab = tokenizer.get_vocab()
        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
        )

        # top_k=2, ntargets=3
        targets = sorted(vocab.keys())[:3]
        outputs = fill_masker(f"This is a {tokenizer.mask_token}", top_k=2, targets=targets)

        # If we use the most probably targets, and filter differently, we should still
        # have the same results
        targets2 = [el["token_str"] for el in sorted(outputs, key=lambda x: x["score"], reverse=True)]
        outputs2 = fill_masker(f"This is a {tokenizer.mask_token}", top_k=3, targets=targets2)

        # They should yield exactly the same result
        self.assertEqual(nested_simplify(outputs), nested_simplify(outputs2))

    def fill_mask_with_duplicate_targets_and_top_k(self, model, tokenizer):
        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
        )
        vocab = tokenizer.get_vocab()
        # String duplicates + id duplicates
        targets = sorted(vocab.keys())[:3]
        targets = [targets[0], targets[1], targets[0], targets[2], targets[1]]
        outputs = fill_masker(f"My name is {tokenizer.mask_token}", targets=targets, top_k=10)

        # The target list contains duplicates, so we can't output more
        # than them
        self.assertEqual(len(outputs), 3)

    def fill_mask_with_multiple_masks(self, model, tokenizer):
        fill_masker = pipeline(
            task="fill-mask",
            model=model,
            tokenizer=tokenizer,
        )

        outputs = fill_masker(
            f"This is a {tokenizer.mask_token} {tokenizer.mask_token} {tokenizer.mask_token}", top_k=2
        )
        self.assertEqual(
            outputs,
            [
                [
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                ],
                [
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                ],
                [
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                    {"sequence": ANY(str), "score": ANY(float), "token": ANY(int), "token_str": ANY(str)},
                ],
            ],
        )
