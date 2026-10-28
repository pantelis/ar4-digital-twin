# Pick-and-place pipeline guide

This guide walks through the pipeline that trains and tests the `pick` and `place` skills on your
twin. For each part it gives the settings that trained working skills on the course's reference
twin, and the reasons behind them. The numbers come from runs on that twin. Your twin differs, so
expect to adjust them.

## What you build and what is fixed

You build the PDDL task, the predicate checks, a vectorized Newton environment around your twin,
the two skills trained with PPO from rsl_rl, a plan executor and a judge. The course fixes three
things. The first is the skill interface in `twin_tools.skill`: the observations, the actions and
the TorchScript file format. The second is the task constants in `twin_tools.task`: the cube, the
box, their placement ranges and `HOLD_S`. The third is the grading evaluation, which runs your two
skill files with the course's own executor, predicate checks and judge. This guide restates parts
of both modules. Where the guide and a module disagree, the module is right.

## The task in PDDL

The domain has two actions. `pick` needs the cube on the table and the gripper empty, and leaves
the cube held. `place` needs the cube held, and leaves it in the box with the gripper empty. The
object type is `item` because the `pddl` package (0.5.1) rejects `object` as a type name.

`domain.pddl`:

```lisp
(define (domain pick-place)
  (:requirements :strips :typing)
  (:types item box)
  (:predicates
    (on ?o - item)
    (holding ?o - item)
    (in ?o - item ?b - box)
    (gripper-empty))
  (:action pick
    :parameters (?o - item)
    :precondition (and (on ?o) (gripper-empty))
    :effect (and (holding ?o) (not (on ?o)) (not (gripper-empty))))
  (:action place
    :parameters (?o - item ?b - box)
    :precondition (holding ?o)
    :effect (and (in ?o ?b) (gripper-empty) (not (holding ?o)))))
```

`problem.pddl`:

```lisp
(define (problem put-the-cube-in-the-box)
  (:domain pick-place)
  (:objects cube - item box - box)
  (:init (on cube) (gripper-empty))
  (:goal (in cube box)))
```

The plan is always `pick` then `place`. You still write it in PDDL, because the predicates give
each skill its reset, its success test and its precondition in the executor.

## Predicate checks on Newton state

Each predicate is a function of the Newton state that returns one boolean per world. Treat the
cube as a box. Treat each jaw as the box that bounds its collision shapes, including the shapes of
any pad or finger welded to it. Give that box a frame on the jaw's body, with x along the jaw's
closing direction, so the jaw's inner face sits at x equal to the box's half extent. If your jaw is
one box with a face toward the cube, as the reference twin's is, the bounding box is the jaw itself.
These definitions and tolerances worked on the reference twin:

| Predicate | True when | Tolerances |
|---|---|---|
| `on` | The cube's lowest point is on the table and the cube is at rest. | 3 mm above the table; speed under 0.05 m/s |
| `holding` | Each jaw's inner face touches the cube, the cube's center lies over both faces, and the cube is off the table. | Gap at most 2 mm; penetration at most 2 mm (twin-check's `GRASP_PENETRATION`); cube bottom at least 0.01 m up |
| `in` | The cube's footprint lies inside the box's inner walls, its bottom is below the rim, and it is at rest. | 1 mm into a wall allowed; rim at `BOX_WALL_HEIGHT`; speed under 0.05 m/s |
| `gripper-empty` | Neither jaw touches the cube: each jaw is clear of it along some axis of the jaw frame. | Clear by more than 2 mm |

Measure heights from the cube's lowest corner, not its center, because a tilted cube sits lower
than its center suggests. Write `in` as `inside` in Python, since `in` is a keyword.

The course evaluation reads your twin's geometry this way too. It accepts collision shapes that
are boxes, spheres, capsules, straight-sided cylinders, cones, ellipsoids and meshes, on the jaws
and on the links. It stops with an error that names the shape for any other type, such as a
barrel-sided cylinder, a plane or a height field. twin-check does not flag those, so keep your
twin's collision shapes to the listed types. A shape that is only visual is not read.

Put the predicates in one module and use it everywhere. The environment resets each world into an
action's precondition with it and decides success with it. The executor refuses an action whose
precondition is false. The judge decides each episode from the logged state with the same
functions, never from the skill's own success signal. If two copies of `holding` drift apart by a
millimeter, a skill can succeed in training and fail in the judge.

The `holding` penetration bound is the one tolerance we are least sure of. It comes from
twin-check's static grasp test. Under motion, the reference pick skill's jaws sat a median 2.6 mm
into the cube when `holding` lapsed, while the cube stayed up. We think the bound is too strict for
a moving arm, but we have not tested a looser one.

## Simulation settings that hold the cube

A held cube is the hard part of the simulation. These settings held it on the GPU solver:

| Setting | Value | Note |
|---|---|---|
| Solver time step | 1e-3 s | the largest swept step that held the cube |
| Control rate | 50 Hz, 20 solver steps per control step | as in Isaac Lab's lift task |
| Episode length | 5 s | as in the lift task |
| Contact time constant | 2e-3 s, damping ratio 1 | MuJoCo's solref; at least 2 time steps |
| Friction | 0.8 on the jaws, the cube, the box and the table | `CUBE_FRICTION` |
| Contact detection gap | 5 mm on the harness's shapes | Newton's default is 0.1 m |
| Self-collision of the twin | off (every twin-twin shape pair filtered) | the twin still collides with the table, the cube and the box |
| Solver | `SolverMuJoCo`, GPU, `cone="elliptic"`, `impratio=10` | friction resists slip as firmly as contact resists penetration |
| Solver capacity per world | `nconmax=128`, `njmax=256` | the defaults (48 and 64) overflow in the full scene |
| Arm drive gains | ke = effort limit / 0.05 rad, kd = effort limit / velocity limit | position mode |
| Jaw drive gains | ke = effort limit / 1e-3 m, kd = effort limit / velocity limit | twin-check's grasp gains |

The time step comes from a sweep that closed the gripper on the cube and held it against gravity
for 2 s, in 1 to 4096 worlds:

| Time step | Slip | Jaw penetration | Result |
|---|---|---|---|
| 2.5e-4 s | 0.26 mm | 0.49 mm | held |
| 5e-4 s | 0.30 mm | 1.68 mm | held |
| 1e-3 s | 0.42 mm | 1.34 mm | held |
| 2e-3 s | meters | 4.9 mm | dropped before 1 s |
| 5e-3 s | meters | 278 mm | jaws passed through |

Every run stayed finite, including the ones that dropped the cube. A finite check alone does not
catch a failed grasp; measure the slip. At 1e-3 s the penetration leaves 0.66 mm of margin to the
2 mm bound, and nothing between 1e-3 and 2e-3 s was tried.

Self-collision is off because MuJoCo collides each link mesh as its convex hull. At an ordinary
holding pose the hulls of link 2 and link 4, and of link 4 and link 6, overlap by about 2.5 mm.
Those contacts pushed against the drives, and the held cube fell out within 5 s. The cost is that a
policy could learn a pose where the real arm hits itself.

The jaw target ramps. When the skill switches the jaw command, the target moves toward open or
closed at one full stroke per 0.1 s (`JAW_RAMP_S`), a little at every solver step. Driven straight
to closed, a jaw at its effort limit meets the cube at about 2.6 m/s, sinks 2.6 mm per solver step
and bounces for most of a second. A ramp applied once per control step, in 3 mm jumps, still lost
the cube in 22% of place resets. The course evaluation applies the same per-solver-step ramp, so
your environment must too.

## The environment

The environment is an rsl_rl `VecEnv` over many copies of one world. Build one world (your twin
from `build.py`, a ground plane at `TABLE_Z`, the cube and the box) and copy it with
`ModelBuilder.replicate`. Step all worlds together, one control step at a time. On a CUDA device,
capture the 20 solver steps of one control step as one CUDA graph, with the jaw ramp inside it.

rsl_rl 5.5 expects this interface:

- `get_observations()` returns a `TensorDict` with one group, `{"policy": obs}`, where `obs` has
  shape (worlds, 37).
- `step(actions)` returns the observations, the rewards (worlds,), the dones (worlds,) and an
  `extras` dictionary with `time_outs` (a boolean per world) and `log` (scalars for TensorBoard).
- `step` resets the worlds that are done before it returns, so the returned observations start
  their new episodes.

A world ends on success (the skill's predicates held for `HOLD_S`, 25 control steps), on time out
after 5 s, when the cube is more than 1 m from the base, or when its state is no longer finite.

### Resets into each action's precondition

Each skill trains from its action's precondition.

`pick` starts with the grasp frame pointing down 0.20 m above the table at (0.30, 0) m, each arm
joint moved by up to 0.1 rad, the jaws open, and the cube and box drawn with
`twin_tools.task.sample_placements`. Solve the home pose once with IK and reuse it.

`place` starts from a holding state. Put the arm at a pose with the grasp frame pointing down, the
cube on the grasp frame and each jaw 1.5 mm from it, and draw the box with `sample_placements`.
Then close the jaws from open, never start them in contact. With the jaws already touching at full
force, the saturated drive lost its damping and the grasp chattered (penetration 0 to 6 mm,
`holding` false on 10 to 20% of steps). Close them with gravity off over 0.2 s, on a schedule that
brings each jaw to rest on the cube before its drive saturates, then turn gravity on for 0.2 s with
the arm held. During those 20 control steps, ignore the policy's actions and give zero reward.
Keep the settling inside the episode: every world steps in one graph, so settling inside the reset
would stall all of them.

The place reset must cover every holding state `pick` can hand over. The chained test showed
why. Our first place resets started the grasp frame 0.10 to 0.20 m above the table, but
pick finishes as soon as the cube clears the table, with the grasp frame 0.027 to 0.148 m up
(median 0.031 m). Place had never seen that, and only 12% of chained episodes finished. Starting
place resets as low as the cube can be held (grasp frame from 0.0225 m, plus a 12 mm margin for
the cube's sag) raised the chain to 34%. The rest of the gap was the arm pose. Those place resets
came from a fixed grid of 3 y values and 2 gripper yaws, while pick ends wherever the cube was, at
any yaw. Every handover had some joint at least 0.2 rad from the nearest grid pose.

So sample place's start the way the cube is sampled. Draw the cube's x, y and yaw with
`sample_placements`, as pick does, and set the cube upright at that yaw with the grasp frame at its
center. Draw the grasp frame's height from the floor up to 0.20 m. The floor is where the cube's
bottom sits 22 mm above the table, the 10 mm `holding` needs plus the 12 mm sag margin, so the
grasp frame starts at 0.0345 m or higher. Turn the last joint so the jaws face the nearest pair of
cube faces. Solving IK for every world at every reset is slow, so we solved it once on a coarse
grid over the cube's x and y ranges and the heights, and interpolated between grid poses. Give the
grid a row at the floor height: interpolation stops at the lowest row, and our grid once started
at 0.04 m, so no start was drawn below it. Our poses landed within 2.5 mm of the target. A few
low poses near the arm's base cannot be reached; draw those again.

With these resets, drawn from 0.04 m, the best chain rose from 37% to 63%. Adding the floor row
did not raise it further. Two more seeds trained from the floor finished between 8% and 40%
chained, and the 63% skill is still the reference place skill. The floor row changes little in
practice, because the 0.05 rad of joint noise already spreads each start by about 15 mm. Only
about 1.5% of settled starts land within 3 mm of pick's median handover height.

### Overlaps and non-finite worlds

A fresh draw can put the arm, the cube and the box into each other, or the arm below the table.
Test every new start, draw the overlapping worlds again (we allowed 100 draws), and log how often a
world runs out of draws. We tested the cube and the box as boxes and the arm as points sampled on
its shapes, all against a 1 mm margin.

Some worlds blow up. When a world's state is no longer finite, end that world alone, reset it,
give it zero reward and count it in the log. Never let one world's NaN reach the PPO update.

## Observations and actions

The observation and the action are fixed by `twin_tools/skill.py`; read its docstring. In short,
the 37 observations are the six joint positions and velocities, the jaw opening, the grasp frame's
position and quaternion, the cube's position and quaternion, the center of the box's bottom face
and the last action, all raw and in the base frame. The seven actions are six arm values and one
jaw value, each clipped to [-1, 1].

The last action is the previous step's action after that clip. A trained policy's mean often
leaves [-1, 1], so it can differ from your policy's raw output. The course evaluation
feeds the clipped action back, so store the clipped one in your environment too. If you store
the raw one, your skill trains on observations it never sees at grading.

The arm actions are relative joint targets. Each target starts at the joint's position when the
skill starts. At every control step it moves by `a * v_max / CONTROL_HZ`, where `v_max` is the
joint's velocity limit, and is clipped to the joint limits. An action of 1 moves the target at the
joint's full speed, and 0 holds it still. A jaw value of 0 or more opens the jaws and a negative
one closes them, through the 0.1 s ramp.

Our first version used absolute targets, the start pose plus 0.5 times the action. With the clip
to [-1, 1], that kept every joint within 0.5 rad of its start, and carrying the cube to the box
needs about 0.9 rad at J1. Place could never succeed. The relative rule removes that limit and also
bounds the commanded speed. That matters, because jerky targets shake the cube loose: random
targets of 0.05 rad per control step kept `holding` true on only 52% of steps, while a smooth
1 s carry over 0.15 m kept 100% of 256 cubes.

## Rewards

Both skills follow the reward terms of Isaac Lab's lift task, with the terms changed to fit each
action. Distances are in meters.

| Term | Definition | pick weight | place weight |
|---|---|---|---|
| `reaching` | 1 - tanh(d / 0.1), d from the grasp frame to the cube's center | 1.0 | |
| `lifted` | 1 when the cube's lowest point is more than 0.04 m above the table | 15.0 | |
| `holding` | 1 when the `holding` predicate is true | 20.0 | |
| `tracking_coarse` | 1 - tanh(d / 0.3), d from the cube to a point 0.08 m above the box's bottom face | | 16.0 |
| `tracking_fine` | 1 - tanh(d / 0.05), same d | | 5.0 |
| `release` | 1 when the cube is over the box's opening, below its rim, and the gripper is empty | | 10.0 |
| `placed` | 1 when `inside` and `gripper-empty` both hold | | 20.0 |
| `action_rate` | squared change of the action since the last control step | -1e-4 | -1e-4 |
| `joint_vel` | squared velocities of the arm joints and the jaws | -1e-4 | -1e-4 |

Multiply the weighted sum by the control step (0.02 s), as Isaac Lab's reward manager does, so the
reward is per second of simulated time. Pick also takes the lift task's curriculum: after 10,000
control steps, near iteration 417, the `action_rate` and `joint_vel` weights become -1e-1. None of
our good pick checkpoints came after that switch, and with the 400-iteration budget below it never
happens. You can keep it or drop it.

A success must not cut off future reward. A world that succeeds ends its episode. If rsl_rl treats
that end as terminal, the skill loses all the `holding` or `placed` reward it would have kept
earning, and success becomes worth less than staying just short of it. Our first pick run learned
exactly that: success peaked at 0.42 and fell to 0.05 while the `holding` term kept rising. Mark
each success in `extras["time_outs"]` as well as in the dones. rsl_rl then bootstraps the value of
that world's last state, as it does for a time out. With this fix, place went from 0.63 to 0.94. A
terminal success bonus of 10 for pick, tried later, made pick worse (0.11 to 0.15) and was removed.

## rsl_rl configuration

The configuration is the `OnPolicyRunner` setup of Isaac Lab's Franka lift task
(`source/isaaclab_tasks/isaaclab_tasks/manager_based/manipulation/lift/config/franka/agents/rsl_rl_ppo_cfg.py`
at tag v2.3.2), with one change: the actor and the critic normalize their observations. The course
feeds your skill raw observations, so the normalizer has to live inside the exported module, and
`export_policy_to_jit` puts it there.

| Setting | Value | Lift task |
|---|---|---|
| `num_steps_per_env` | 24 | 24 |
| `max_iterations` | 400 (set by the time budget and the seed runs, see below) | 1500 |
| `save_interval` | 50 | 50 |
| `obs_groups` | `{"actor": ["policy"], "critic": ["policy"]}` | same |
| actor and critic `hidden_dims` | [256, 128, 64] | same |
| `activation` | `elu` | same |
| `obs_normalization` | `True` | `False` (the one change) |
| actor distribution | `GaussianDistribution`, `init_std` 1.0 | same |
| `value_loss_coef` | 1.0 | same |
| `use_clipped_value_loss` | `True` | same |
| `clip_param` | 0.2 | same |
| `entropy_coef` | 0.006 | same |
| `num_learning_epochs` | 5 | same |
| `num_mini_batches` | 4 | same |
| `learning_rate` | 1e-4 | same |
| `schedule` | `adaptive` | same |
| `gamma` | 0.98 | same |
| `lam` | 0.95 | same |
| `desired_kl` | 0.01 | same |
| `max_grad_norm` | 1.0 | same |
| `check_for_nan` | `True` | |

Train with 4096 worlds. We used rsl-rl-lib 5.5.1, Newton 1.7.0 and warp 1.18.0.

## Training budget and what to expect

On an RTX PRO 6000 Blackwell, one pick iteration at 4096 worlds took 2.13 s once it settled, about
2.04 s collecting and 0.09 s learning. The first ten iterations are faster because the arms start
still. Place is slower, because every world holds the cube and the solver has more contacts; it took
3.6 to 4.4 s per iteration while sharing the GPU with a pick run.

On a Colab T4, pick took 14.1 s per iteration at 4096 worlds and used 3.7 GB of GPU memory. That is
about 6.6 times slower, so two hours fit about 500 iterations. The budget is 400 iterations, about
1.6 hours on a T4, for the reason the seed runs below give. Save checkpoints every 50 iterations to
Google Drive. We ended a T4 session at iteration 217, and a new one resumed from the iteration 200
checkpoint and carried on.

We trained pick with four seeds and place with three, each for 840 iterations on the same
configuration. Every saved checkpoint was screened on 128 fresh episodes, and the best three and the
final export were then evaluated on 512.

| Skill | Seed | Best checkpoint | Best success | Final export (iteration 840) |
|---|---|---|---|---|
| pick | 0 | 250 | 0.86 | 0.16 |
| pick | 1 | 840 | 0.40 | 0.40 |
| pick | 2 | 840 | 0.12 | 0.12 |
| pick | 3 | 300 | 0.90 | 0.10 |
| place | 0 | 650 | 0.98 | 0.96 |
| place | 1 | 450 | 0.97 | 0.97 |
| place | 2 | 150 | 0.99 | 0.94 |

Place is reliable: every seed passed 0.97, and its last checkpoint is nearly as good as its best.
Pick is not. Two of the four seeds reached 0.86 and 0.90, and the other two never passed 0.40. On
both good seeds, the checkpoints that screened at 0.80 or more fell between iterations 250 and 350,
and success then fell fast: seed 3 went from 0.90 at iteration 350 to 0.50 at 400. By iteration 500
every pick seed screened between 0.06 and 0.15. A T4 run with seed 1 ended at 0.055 after 500
iterations, so the T4 itself did not change the outcome.

Plan your pick training around this. Train at least two seeds, which takes two T4 sessions. Keep every
checkpoint, screen each one on fresh episodes, and export the best, never the last. A run that has
not passed 0.5 by iteration 350 is unlikely to recover; start another seed instead.

The policy's action standard deviation grows in every run, from 1.0 to about 8 to 10 for pick and
about 13 for place. Sampled actions then sit at the clip most of the time. The exported skill acts
with the mean, so this does not reach the course, but it may explain why pick degrades late.

## Evaluating and exporting a skill

Evaluate a skill the way the course will. Start one fresh episode in each of 512 worlds, drawn with
a seed your training never used. Load the exported file with `twin_tools.skill.load_skill`, feed it
raw observations, and count the episodes that end on success. A time out, a cube beyond 1 m and a
non-finite world are failures.

Export with rsl_rl's `export_policy_to_jit`, which writes a TorchScript module with the observation
normalizer inside. Then check the file against the interface:

```python
from twin_tools.skill import check_skill

problems = check_skill("skills/pick.pt")
print(problems or "pick.pt fits the interface")
```

An empty list means the course can run the file. It does not say whether the skill is any good.

Then chain the skills, which is what the grading evaluation does. Start fresh pick episodes, run
pick until `holding` has lasted `HOLD_S`, and hand each world to place at once. At the handover,
restart the arm targets at the current joint positions and the last action at zero, as a skill's
start requires. Give each skill up to 5 s. Count the worlds that end with the cube in the box and
the gripper empty, and sort the failures by where they happened: pick timed out, cube lost in pick,
cube dropped outside the box, and so on.

Choose the place checkpoint by its chained score, not by its own success rate. The twelve place
checkpoints we chained from full-range resets scored 0.95 to 0.99 on their own resets, where
measured. Chained with the same pick (seed 3 at iteration 300, about 89% handed over, 512
episodes), they finished between 8% and 63%. The best one dropped the cube outside the box in 18%
of episodes and lost it during place in 9%. With the older
grid resets the best chain was 37%, with 46% dropped outside the box. We do not yet know why
checkpoints that look the same on place's own resets differ this much on pick's handovers.

## Mistakes we made

- A success that ended the episode as terminal taught pick to avoid success; mark it in `time_outs`.
- Absolute action targets capped every joint at 0.5 rad from the start; use relative targets.
- A jaw driven straight to closed bounced off the cube; ramp the target over 0.1 s at every solver step.
- Place resets that started with the jaws already closed chattered; close them from open with gravity off.
- Twin self-collision on convex hulls pushed the cube out of the jaws; filter twin-twin contacts.
- A 2e-3 s time step dropped the cube while every value stayed finite; check the slip, not just finiteness.
- Place trained from states pick never hands over; cover pick's end heights and poses in place's resets.
- A place skill at 0.99 on its own resets chained at 37%; score place checkpoints on pick's handovers.
- The last checkpoint of a good pick run scored 0.10 to 0.16 against 0.86 to 0.90 for its best; keep and export the best.
- One good pick run looked like a good configuration, and two of four seeds never passed 0.40; train a second seed before you trust a number.
