#!/usr/bin/env python3

from aws_cdk import core

from cold_start_benchmark.cold_start_benchmark_stack import ColdStartBenchmarkStack


app = core.App()
ColdStartBenchmarkStack(app, "cold-start-benchmark")

app.synth()
