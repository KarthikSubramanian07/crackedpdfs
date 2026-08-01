# Example triplets

`triplets.jsonl` contains fifteen exact metadata triplets selected from the frozen paper corpus. Each line is one JSON object with shared triplet metadata and three ordered members:

1. benign original;
2. matched benign confounder; and
3. injected attack.

The selection includes five examples from each split and multiple attack and confounder families.

The `path` fields are the original corpus-relative locations. The corresponding PDF binaries are not duplicated in Git; they are available in the [published dataset archives at revision `245bc98`](https://huggingface.co/datasets/volkthienpreecha/crackedpdfs/tree/245bc98ec7e838346ee6fd5bdf5fed1b16d2a3e5/pdfs).
