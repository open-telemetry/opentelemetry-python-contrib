from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric


def evaluate_answer_relevancy_metric(prompt:str, output:str, retrieval_context:list) -> AnswerRelevancyMetric:
    test_case = LLMTestCase(input=prompt,
                            actual_output=output,
                            retrieval_context=retrieval_context,)
    relevancy_metric = AnswerRelevancyMetric(threshold=0.5)
    relevancy_metric.measure(test_case)
    print(relevancy_metric.score, relevancy_metric.reason)
    return relevancy_metric