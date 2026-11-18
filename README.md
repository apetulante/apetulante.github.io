# Abbie's AI Tutorials

In-depth, notebook-based tutorials on modern AI/ML, from architectures, to training and
fine-tuning, and inference. 

All are written by me, AI Researcher, and former postdoctoral scholar at Vanderbilt Data Science.

You can find the main blog here: **https://apetulante.github.io/**

Each post is a hands-on Jupyter notebook that builds the idea up from scratch, with math, custom diagrams, and runnable code. Browse the full set below.

### Tutorials

#### Architectures
- **[The Transformer Architecture](https://apetulante.github.io/posts/Transformer/transformer_tutorial.html)** - a from-scratch guide to the full encoder-decoder transformer: attention, multi-head attention, positional encodings, assembling and training the model, and how to evaluate it, built up piece by piece.
- **[The U-Net Architecture](https://apetulante.github.io/posts/UNet-Tutorial/UNet_Tutorial.html)** - a complete guide to U-Net, covering every part of a layer from the convolution operation to pooling, and what makes U-Nets so effective for image reconstruction.

#### Training & Fine-Tuning
- **[Fine-Tuning LLaVA with and without LoRA](https://apetulante.github.io/posts/LLaVA-Astronomy/LLaVA_GalaxyZoo.html)** - a deep dive into the LLaVA architecture, fine-tuned (with and without LoRA) to classify galaxy morphologies from GalaxyZoo2 images.
- **[PEFT Deep Dive: LoRA](https://apetulante.github.io/posts/PEFT-LoRA/PEFT_LoRA.html)** - the mathematical foundations and a practical implementation of LoRA, one of the most common parameter-efficient fine-tuning methods.
- **[RL for LLMs](https://apetulante.github.io/posts/RL-for-LLMs/RL_for_LLMs.html)** - an in-depth guide to reinforcement learning with proximal policy optimization (PPO), focused on how it applies to modern large language models (including from human feedback).

#### Inference & Caching
- **[KV Caching](https://apetulante.github.io/posts/KV-Caching/kv_caching.html)** - how KV caching is implemented for LLMs, with a practical example on LLaMA 3.2 1B.
- **[Prompt Caching](https://apetulante.github.io/posts/Prompt-Caching/prompt_caching.html)** - a modular approach to KV caching: how and why it works, with a practical implementation on LLaMA 3.2 1B.

----

#### License & Reuse

© Abbie Petulante. The tutorials here - text, diagrams, and figures -  are licensed under CC BY 4.0. 
You're welcome to reuse, adapt, and share any part  of them (including diagrams and excerpts) in your own work, as long as you give credit. Code snippets are provided under the MIT License.
  
---

*Built with [Quarto](https://quarto.org). Each tutorial also opens directly in Google Colab via the badge at the top of the post.*
