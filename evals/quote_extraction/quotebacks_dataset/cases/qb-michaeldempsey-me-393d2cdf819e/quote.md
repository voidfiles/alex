> A long time ago, when OpenAI still did RL in games / simulation, they were very into [self-play](https://openai.com/research/competitive-self-play). You run agents against copies of themselves, score their interactions, and update the models towards interactions with higher reward. Given enough time, they learn complex strategies through competition. At the time, I remember Ilya said they cared because self-play was a method to turn compute into data. You run your model, get data from your model’s interactions with the environment, funnel it back in, and get an exponential improvement in your Elo curves. What was quickly clear was that this was true, but only in the narrow regime where self-play was possible. In practice that usually meant game-like environments with at most a few hundred different entities, plus a ground truth reward function that was not too easy or hard, and an easy ability to reset and run faster than real time. Without all those qualities, self-play sputtered and died with nothing to show for it besides warmer GPUs.

Selected by Michael Dempsey.

Source: https://www.alexirpan.com/2024/01/10/ai-timelines-2024.html

Selection page: https://www.michaeldempsey.me/blog/2024/01/23/collective-intelligence-multi-agent-debate-agi/
