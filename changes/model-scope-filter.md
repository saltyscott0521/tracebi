### Shared model scope across the chain

A **Model** control on the chain strip filters Pipelines, Data model,
Explore, and Reports to one connected model (`?model=<name>`). Pipelines
built with `model_pipeline` expose their model on the API; reports match by
the `reports/<model>/…` path convention. Sidebar and chain links keep the
scope when you move between pages.
