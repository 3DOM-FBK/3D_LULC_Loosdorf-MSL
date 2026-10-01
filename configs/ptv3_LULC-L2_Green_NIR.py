_base_ = ["../_base_/default_runtime.py"]
# misc custom setting
batch_size = 16 # bs: total bs in all gpus
mix_prob = 0
empty_cache =False 
enable_amp = False #True

# model settings
model = dict(
    type="DefaultSegmentorV2",
    num_classes=20,
    backbone_out_channels=64,
    backbone=dict(
        type="PT-v3m1",
        in_channels=6, #xyz + green + nir + normz
        order=["z", "z-trans", "hilbert", "hilbert-trans"],
        stride=(2, 2, 2, 2),
        enc_depths=(2, 2, 2, 6, 2),
        enc_channels=(32, 64, 128, 256, 512),
        enc_num_head=(2, 4, 8, 16, 32),
        enc_patch_size=(128, 128, 128, 128, 128),
        dec_depths=(2, 2, 2, 2),
        dec_channels=(64, 64, 128, 256),
        dec_num_head=(4, 4, 8, 16),
        dec_patch_size=(128, 128, 128, 128),
        mlp_ratio=4,
        qkv_bias=True,
        qk_scale=None,
        attn_drop=0.0,
        proj_drop=0.0,
        drop_path=0.1,
        shuffle_orders=True,
        pre_norm=True,
        enable_rpe=True,
        enable_flash=False,
        upcast_attention=True,
        upcast_softmax=True,
        cls_mode=False,
        pdnorm_bn=False,
        pdnorm_ln=False,
        pdnorm_decouple=True,
        pdnorm_adaptive=False,
        pdnorm_affine=True,
        pdnorm_conditions=("ScanNet", "S3DIS", "Structured3D"),
    ),
    criteria=[
        dict(type="CrossEntropyLoss",loss_weight=1.0, 
        weight=[3.5783e+00, 6.1719e-02, 4.8590e+00, 2.6749e+01, 1.0672e+00, 1.9946e+00, 8.3701e-01, 3.9172e+00, 4.2601e+01, 6.4787e+02, 1.0516e+02, 2.2361e+02, 2.7272e+02, 1.2407e+02, 6.3591e+02, 7.9868e+01, 5.5985e+01, 3.8545e+00, 1.2330e+02, 2.7596e+01],
        ignore_index=-1),
        dict(type="LovaszLoss", mode="multiclass", loss_weight=1.0, ignore_index=-1),
    ],
)


# scheduler settings
epoch = 1000
optimizer = dict(type="AdamW", lr=0.001, weight_decay=0.05)
scheduler = dict(
    type="OneCycleLR",
    # max_lr=[0.006, 0.0006],
    max_lr=[0.001, 0.0001],
    # pct_start=0.05,
    pct_start=0.01,
    anneal_strategy="cos",
    div_factor=10.0,
    final_div_factor=1000.0,
)
param_dicts = [dict(keyword="block", lr=0.0006)]

# dataset settings
dataset_type = "LoosdorfDataset"
data_root = "data/Loosdorf-MSL-L2"
ignore_index = -1
names = [
    "asphalt",
    "soil",
    "road",
    "water",
    "low_vegetation",
    "medium_vegetation",
    "high_vegetation",
    "roof",
    "facade",
    "chimney",
    "solar_panel",
    "vehicle",
    "electric_tower",
    "cable",
    "pole",
    "bridge",
    "fence",
    "sport_area",
    "road_marking",
    "other",
]

data = dict(
    num_classes=20,
    ignore_index=ignore_index,
    names=names,
    train=dict(
        type=dataset_type,
        split="train",
        data_root=data_root,
        transform=[
            # dict(type="RandomDropout", dropout_ratio=0.2, dropout_application_ratio=0.2),
            # dict(type="RandomRotateTargetAngle", angle=(1/2, 1, 3/2), center=[0, 0, 0], axis='z', p=0.75),
            dict(type="RandomRotate", angle=[-1, 1], axis="z", center=[0, 0, 0], p=0.5),
            # dict(type="RandomRotate", angle=[-1/6, 1/6], axis='x', p=0.5),
            # dict(type="RandomRotate", angle=[-1/6, 1/6], axis='y', p=0.5),
            dict(type="RandomScale", scale=[0.9, 1.1]),
            # dict(type="RandomShift", shift=[0.2, 0.2, 0.2]),
            dict(type="RandomFlip", p=0.5),
            dict(type="RandomJitter", sigma=0.005, clip=0.02),
            # dict(type="ElasticDistortion", distortion_params=[[0.2, 0.4], [0.8, 1.6]]),
            dict(
                type="GridSample",
                grid_size=0.1, #0.1, #0.24,#0.12,
                hash_type="fnv",
                mode="train",
                keys=("coord", "color", "segment"),
                return_grid_coord=True,
            ),
            # dict(type="SphereCrop", point_max=1000000, mode="random"),
            # dict(type="CenterShift", apply_z=False),
            # dict(type="NormalizeColor"),
            dict(type="ToTensor"),
            dict(
                type="Collect",
                keys=("coord", "grid_coord", "segment"),
                feat_keys=("coord", "color"),
            ),
        ],
        test_mode=False,
        ignore_index=ignore_index,
    ),
    val=dict(
        type=dataset_type,
        split="val",
        data_root=data_root,
        transform=[
            # dict(type="PointClip", point_cloud_range=(-51.2, -51.2, -4, 51.2, 51.2, 2.4)),
            dict(
                type="GridSample",
                grid_size=0.1, #0.1, #0.24,#0.12,
                hash_type="fnv",
                mode="train",
                keys=("coord", "color", "segment"),
                return_grid_coord=True,
            ),
            # dict(type="SphereCrop", point_max=1000000, mode='center'),
            # dict(type="NormalizeColor"),
            dict(type="ToTensor"),
            dict(
                type="Collect",
                keys=("coord", "grid_coord", "segment"),
                feat_keys=("coord", "color"),
            ),
        ],
        test_mode=False,
        ignore_index=ignore_index,
    ),
    test=dict(
        type=dataset_type,
        split="test",
        data_root=data_root,
        # transform=[dict(type="CenterShift", apply_z=True), dict(type="NormalizeColor")],
        transform=[dict(type="CenterShift", apply_z=True)],
        # transform=[
            # dict(type="Copy", keys_dict={"segment": "origin_segment"}),  
            # dict(type="Copy"),
            # dict(type="CenterShift", apply_z=True),
            # dict(type="NormalizeColor"),
            # dict(
                # type="GridSample",
                # grid_size=0.25,
                # hash_type="fnv",
                # mode="train",
                # keys=("coord", "color", "segment"),
                # return_inverse=True,
            # ),
        # ],
        test_mode=True,
        test_cfg=dict(
            voxelize=dict(
                type="GridSample",
                grid_size=0.1, #0.1, #0.24,#0.12,
                hash_type="fnv",
                mode="test",
                return_grid_coord=True,
                keys=("coord", "color"),
            ),
            crop=None,
            post_transform=[
                dict(type="ToTensor"),
                dict(
                    type="Collect",
                    keys=("coord", "grid_coord", "index"),
                    feat_keys=("coord", "color"),
                ),
            ],
            aug_transform=[
                [dict(type="RandomScale", scale=[0.9, 0.9])],
                [dict(type="RandomScale", scale=[0.95, 0.95])],
                [dict(type="RandomScale", scale=[1, 1])],
                [dict(type="RandomScale", scale=[1.05, 1.05])],
                [dict(type="RandomScale", scale=[1.1, 1.1])],
                [
                    dict(type="RandomScale", scale=[0.9, 0.9]),
                    dict(type="RandomFlip", p=1),
                ],
                [
                    dict(type="RandomScale", scale=[0.95, 0.95]),
                    dict(type="RandomFlip", p=1),
                ],
                [dict(type="RandomScale", scale=[1, 1]), dict(type="RandomFlip", p=1)],
                [
                    dict(type="RandomScale", scale=[1.05, 1.05]),
                    dict(type="RandomFlip", p=1),
                ],
                [
                    dict(type="RandomScale", scale=[1.1, 1.1]),
                    dict(type="RandomFlip", p=1),
                ],
            ],
        ),
        ignore_index=ignore_index,
    ),
)
