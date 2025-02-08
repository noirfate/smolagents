from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

endpoint = "http://0.0.0.0:6006/v1/traces"
trace_provider = TracerProvider()
trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint)))

SmolagentsInstrumentor().instrument(tracer_provider=trace_provider)

agent = CodeAgent(
    tools=[DuckDuckGoSearchTool()], 
    model=LiteLLMModel(
        model_id="o3-mini",
        api_base="https://xxx",  # 设置你的基础 URL
        api_key="sk-xxx"  # 替换成你的真实 API key
    ),
    additional_authorized_imports=["*"],
)

agent.run("本机IP地址是多少")