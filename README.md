
# Serverless Computation Cold Start Benchmark

## 1. Description
'Does serverless make sense?' I keep asking myself this question after spending lots of time reading about AWS Serverless infrastructure. Obviously there are massive exciting features Serverless provides to us, for example 'Pay as you go', 'Infra, Deployment, Config as(is) code', 'Elasticity', 'Business logic focusing' etc. etc. Exciting right? BUT, if read these words again and slower, I feel like someone is hiding something:

1. Pay as you go: Nobody says you will save money OK?
2. Infra, Deployment, Config as(is) code: Automation is great. But without Serverless we have bash right?
3. Elasticity: Oh BTW, there will be no elasticity if your function needs more than 5 mins. And, yes, sorry about that, if you have LSI enabled, your partition size should be no more than 10GB.
4. Business logic focusing: Ha! You think you could focuse 100% on your business logic if you migrate to Serverless? YOU ARE WRONG! Come and get your AWS Certs baby.

So, short answer to the question - "It depends." From the learning point of view, Serverless can abstract low-level structures to easily-understandable concepts. But at the same time, it also brings a new set of knowledge into learning scope. To better understand and remember those new rules, you still need to go deeper. From the business point of view, Serverless cannot resolve everything. One of the most pain points, on which I will focus in this project, is cold start latency. This could block latency-sensitive business usecasees from being migrated onto Serverless.

To better understand Serverless, I plan to build a Serverless website on AWS. And, further more, the content of this website will be a Cold Start Latency Benchmark of language, settings, and provider. 

## 2. Design
