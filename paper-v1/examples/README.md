# Example triplets

`triplets.jsonl` contains fifteen exact metadata triplets selected from the frozen paper corpus. Each line is one JSON object with shared triplet metadata and three ordered members:

1. benign original;
2. matched benign confounder; and
3. injected attack.

The selection includes five examples from each split and multiple attack and confounder families.

The `path` fields are the original corpus-relative locations. The corresponding PDF binaries are not duplicated in Git; they are available in the [published dataset archives at revision `4a9ad89`](https://huggingface.co/datasets/volkthienpreecha/crackedpdfs/tree/4a9ad89a9f42bb18681b608c07b643cd77491ea5/pdfs).
