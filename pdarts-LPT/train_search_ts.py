import os
import sys
import time
import glob
import numpy as np
import torch
import utils
import logging
import argparse
import torch.nn as nn
import torch.utils
import torch.nn.functional as F
import torchvision.datasets as dset
import torch.backends.cudnn as cudnn
import copy
from model_search import Network
from genotypes import PRIMITIVES
from genotypes import Genotype
from teacher import *
from teacher_update import *
import custom_dataset
import mendely_dataloader as loader

parser = argparse.ArgumentParser("cifar")
parser.add_argument('--workers', type=int, default=2,
                    help='number of workers to load dataset')
parser.add_argument('--batch_size', type=int, default=96, help='batch size')
parser.add_argument('--learning_rate', type=float,
                    default=0.005, help='init learning rate')
parser.add_argument('--learning_rate_min', type=float,
                    default=0.0, help='min learning rate')
parser.add_argument('--momentum', type=float, default=0.9, help='momentum')
parser.add_argument('--weight_decay', type=float,
                    default=3e-4, help='weight decay')
parser.add_argument('--report_freq', type=float,
                    default=50, help='report frequency')
parser.add_argument('--epochs', type=int, default=25,
                    help='num of training epochs')
parser.add_argument('--init_channels', type=int,
                    default=16, help='num of init channels')
parser.add_argument('--layers', type=int, default=5,
                    help='total number of layers')
parser.add_argument('--cutout', action='store_true',
                    default=False, help='use cutout')
parser.add_argument('--cutout_length', type=int,
                    default=16, help='cutout length')
parser.add_argument('--drop_path_prob', type=float,
                    default=0.3, help='drop path probability')
parser.add_argument('--save', type=str,
                    default='', help='experiment path')
parser.add_argument('--seed', type=int, default=2, help='random seed')
parser.add_argument('--grad_clip', type=float,
                    default=5, help='gradient clipping')
parser.add_argument('--train_portion', type=float,
                    default=0.5, help='portion of training data')
parser.add_argument('--arch_learning_rate', type=float,
                    default=6e-4, help='learning rate for arch encoding')
parser.add_argument('--arch_weight_decay', type=float,
                    default=1e-3, help='weight decay for arch encoding')
parser.add_argument('--tmp_data_dir', type=str,
                    default='/tmp/cache/', help='temp data dir')
parser.add_argument('--note', type=str, default='try',
                    help='note for this run')
# parser.add_argument('--dropout_rate', action='append',
#                     default=[], help='dropout rate of skip connect')
parser.add_argument('--dropout_rate', action='append',
                    default=['0.1', '0.4', '0.7'], help='dropout rate of skip connect')
parser.add_argument('--add_width', action='append',
                    default=['0'], help='add channels')
# parser.add_argument('--add_layers', action='append',
#                     default=['0'], help='add layers')
parser.add_argument('--add_layers', action='append',
                    default=['6', '12'], help='add layers')
parser.add_argument('--cifar100', action='store_true',
                    default=False, help='search with cifar100 dataset')

parser.add_argument('--gpu', type=str, default='0')
parser.add_argument('--weight_gamma', type=float, default=1.0)
parser.add_argument('--weight_lambda', type=float, default=1.0)
parser.add_argument('--model_v_learning_rate', type=float, default=3e-4)
parser.add_argument('--model_v_weight_decay', type=float, default=1e-3)
parser.add_argument('--learning_rate_w', type=float, default=0.025)
parser.add_argument('--learning_rate_h', type=float, default=0.025)
parser.add_argument('--weight_decay_w', type=float, default=3e-4)
parser.add_argument('--weight_decay_h', type=float, default=3e-4)
parser.add_argument('--is_parallel', type=int, default=0)
parser.add_argument('--teacher_arch', type=str, default='18')
parser.add_argument('--is_cifar100', type=int, default=0)
parser.add_argument('--dataset_path', type=str, default='/local/kaggle/blood_cell/', help='location of the data corpus')
# parser.add_argument('--dataset_path', type=str, default='../kaggle/blood_cell/', help='location of the data corpus')
parser.add_argument('--local_mount', type=int, default=1, help='1 use /local on kubectl, 0 use persistent volume')
args = parser.parse_args()
os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu


args.save = '{}search-{}-{}'.format(args.save,
                                    args.note, time.strftime("%Y%m%d-%H%M%S"))
utils.create_exp_dir(args.save, scripts_to_save=glob.glob('*.py'))

log_format = '%(asctime)s %(message)s'
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format=log_format, datefmt='%m/%d %I:%M:%S %p')
fh = logging.FileHandler(os.path.join(args.save, 'log.txt'))
fh.setFormatter(logging.Formatter(log_format))
logging.getLogger().addHandler(fh)

# if args.cifar100:
#     CIFAR_CLASSES = 100
#     data_folder = '../data'
# else:
#     CIFAR_CLASSES = 10
#     data_folder = '../data'

NUM_CLASSES = 8


def main():
    if not torch.cuda.is_available():
        logging.info('No GPU device available')
        sys.exit(1)
    np.random.seed(args.seed)
    cudnn.benchmark = True
    torch.manual_seed(args.seed)
    cudnn.enabled = True
    torch.cuda.manual_seed(args.seed)
    logging.info("args = %s", args)

    #  prepare dataset
    # if args.cifar100:
    #     train_transform, valid_transform = utils._data_transforms_cifar100(
    #         args)
    # else:
    #     train_transform, valid_transform = utils._data_transforms_cifar10(args)
    # if args.cifar100:
    #     train_data = dset.CIFAR100(
    #         root=args.tmp_data_dir, train=True, download=True, transform=train_transform)
    # else:
    #     train_data = dset.CIFAR10(
    #         root=args.tmp_data_dir, train=True, download=True, transform=train_transform)
    
    if args.teacher_arch == '18':
        teacher_w = resnet18().cuda()
    elif args.teacher_arch == '50':
        teacher_w = resnet50().cuda()
    elif args.teacher_arch == '101':
        teacher_w = resnet101().cuda()

    # if args.cifar100:
    #     teacher_h = nn.Linear(
    #         512 * teacher_w.block.expansion, CIFAR100_CLASSES).cuda()
    # else:
    #     teacher_h = nn.Linear(
    #         512 * teacher_w.block.expansion, CIFAR_CLASSES).cuda()
    teacher_h = nn.Linear(512 * teacher_w.block.expansion, NUM_CLASSES).cuda()
    teacher_v = nn.Linear(512 * teacher_w.block.expansion, 2).cuda()

    # num_train = len(train_data)
    # indices = list(range(num_train))
    # split = int(np.floor(args.train_portion * num_train))

    # train_queue = torch.utils.data.DataLoader(
    #     train_data, batch_size=args.batch_size,
    #     sampler=torch.utils.data.sampler.SubsetRandomSampler(indices[:split]),
    #     pin_memory=True, num_workers=args.workers)

    # valid_queue = torch.utils.data.DataLoader(
    #     train_data, batch_size=args.batch_size,
    #     sampler=torch.utils.data.sampler.SubsetRandomSampler(
    #         indices[split:num_train]),
    #     pin_memory=True, num_workers=args.workers)
    # # the dataset for data selection. can be imagenet or so.
    # external_queue = torch.utils.data.DataLoader(
    #     train_data, batch_size=args.batch_size,
    #     sampler=torch.utils.data.sampler.SubsetRandomSampler(
    #         indices[split:num_train]),
    #     pin_memory=False, num_workers=4)

    # dataset_path = args.dataset_path
    # train_data, _, _ = custom_dataset.parse_dataset(dataset_path) 
    # train_queue, valid_queue, external_queue = custom_dataset.preprocess_data(
    #     train_data, _, args.batch_size, train_search=True)
    if args.local_mount == 0:
        dataloaders = loader.get_dataloaders(batch_size = args.batch_size, train_search=True)
    else:
        path = '/local/kaggle/PBC_dataset_split/PBC_dataset_split'
        dataloaders = loader.get_dataloaders(batch_size=args.batch_size, train_search=True, data_dir=path)
  
    torch.cuda.empty_cache()  # Clear GPU Memory
    
    # build Network
    criterion = nn.CrossEntropyLoss()
    criterion = criterion.cuda()
    switches = []
    for i in range(14):
        switches.append([True for j in range(len(PRIMITIVES))])
    switches_normal = copy.deepcopy(switches)
    switches_reduce = copy.deepcopy(switches)
    # To be moved to args
    num_to_keep = [5, 3, 1]
    num_to_drop = [3, 2, 2]
    if len(args.add_width) == 3:
        add_width = args.add_width
    else:
        add_width = [0, 0, 0]
    if len(args.add_layers) == 3:
        add_layers = args.add_layers
    else:
        add_layers = [0, 6, 12]
    if len(args.dropout_rate) == 3:
        drop_rate = args.dropout_rate
    else:
        drop_rate = [0.0, 0.0, 0.0]
    eps_no_archs = [10, 10, 10]
    for sp in range(len(num_to_keep)):
        # model = Network(args.init_channels + int(add_width[sp]), CIFAR_CLASSES, args.layers + int(
        #     add_layers[sp]), criterion, switches_normal=switches_normal, switches_reduce=switches_reduce, p=float(drop_rate[sp]))
        model = Network(args.init_channels + int(add_width[sp]), NUM_CLASSES, args.layers + int(
            add_layers[sp]), criterion, switches_normal=switches_normal, switches_reduce=switches_reduce, p=float(drop_rate[sp]))
        model = nn.DataParallel(model)
        model = model.cuda()
        logging.info("param size = %fMB", utils.count_parameters_in_MB(model))
        network_params = []
        for k, v in model.named_parameters():
            if not (k.endswith('alphas_normal') or k.endswith('alphas_reduce')):
                network_params.append(v)
        optimizer = torch.optim.SGD(
            network_params,
            args.learning_rate,
            momentum=args.momentum,
            weight_decay=args.weight_decay)
        optimizer_w = torch.optim.SGD(
            teacher_w.parameters(),
            args.learning_rate_w,
            momentum=args.momentum,
            weight_decay=args.weight_decay_w)
        optimizer_h = torch.optim.SGD(
            teacher_h.parameters(),
            args.learning_rate_h,
            momentum=args.momentum,
            weight_decay=args.weight_decay_h)
        optimizer_v = torch.optim.Adam(
            teacher_v.parameters(),
            lr=args.model_v_learning_rate,
            betas=(0.5, 0.999),
            weight_decay=args.model_v_weight_decay)
        optimizer_a = torch.optim.Adam(model.module.arch_parameters(),
                                       lr=args.arch_learning_rate,
                                       betas=(0.5, 0.999),
                                       weight_decay=args.arch_weight_decay)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, float(args.epochs), eta_min=args.learning_rate_min)
        scheduler_w = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer_w, float(args.epochs), eta_min=args.learning_rate_min)
        scheduler_h = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer_h, float(args.epochs), eta_min=args.learning_rate_min)
        sm_dim = -1
        epochs = args.epochs
        eps_no_arch = eps_no_archs[sp]
        scale_factor = 0.2
        for epoch in range(epochs):
            lr = scheduler.get_lr()[0]
            lr_w = scheduler_w.get_lr()[0]
            lr_h = scheduler_h.get_lr()[0]
            logging.info('epoch %d lr %e lr_w %e lr_h %e', epoch, lr, lr_w, lr_h)
            # lr = scheduler.get_lr()[0]
            # logging.info('Epoch: %d lr: %e', epoch, lr)
            epoch_start = time.time()
            # training
            if epoch < eps_no_arch:
                model.module.p = float(
                    drop_rate[sp]) * (epochs - epoch - 1) / epochs
                model.module.update_p()
                train_acc, train_obj = train(
                    # train_queue, valid_queue,external_queue,
                    dataloaders[0], dataloaders[1], dataloaders[2],
                    model,
                    teacher_w,
                    teacher_h,
                    teacher_v,
                    network_params,
                    criterion, optimizer, optimizer_a,
                    optimizer_w,
                    optimizer_h,
                    optimizer_v,
                    lr,
                    lr_w,
                    lr_h,
                    train_arch=False)
            else:
                model.module.p = float(
                    drop_rate[sp]) * np.exp(-(epoch - eps_no_arch) * scale_factor)
                model.module.update_p()
                train_acc, train_obj = train(
                    # train_queue, valid_queue,external_queue,
                    dataloaders[0], dataloaders[1], dataloaders[2],
                    model,
                    teacher_w,
                    teacher_h,
                    teacher_v,
                    network_params,
                    criterion, optimizer, optimizer_a,
                    optimizer_w,
                    optimizer_h,
                    optimizer_v,
                    lr,
                    lr_w,
                    lr_h,
                    train_arch=True)
            scheduler.step()
            scheduler_w.step()
            scheduler_h.step()
            logging.info('Train_acc %f', train_acc)
            epoch_duration = time.time() - epoch_start
            logging.info('Epoch time: %ds', epoch_duration)
            # validation
            if epochs - epoch < 5:
                # valid_acc, valid_obj = infer(valid_queue, model, criterion)
                valid_acc, valid_obj = infer(dataloaders[1], model, criterion)
                logging.info('Valid_acc %f', valid_acc)
        utils.save(model, os.path.join(args.save, 'weights.pt'))
        print('------Dropping %d paths------' % num_to_drop[sp])
        # Save switches info for s-c refinement.
        if sp == len(num_to_keep) - 1:
            switches_normal_2 = copy.deepcopy(switches_normal)
            switches_reduce_2 = copy.deepcopy(switches_reduce)
        # drop operations with low architecture weights
        arch_param = model.module.arch_parameters()
        normal_prob = F.softmax(arch_param[0], dim=sm_dim).data.cpu().numpy()
        for i in range(14):
            idxs = []
            for j in range(len(PRIMITIVES)):
                if switches_normal[i][j]:
                    idxs.append(j)
            if sp == len(num_to_keep) - 1:
                # for the last stage, drop all Zero operations
                drop = get_min_k_no_zero(
                    normal_prob[i, :], idxs, num_to_drop[sp])
            else:
                drop = get_min_k(normal_prob[i, :], num_to_drop[sp])
            for idx in drop:
                switches_normal[i][idxs[idx]] = False
        reduce_prob = F.softmax(arch_param[1], dim=-1).data.cpu().numpy()
        for i in range(14):
            idxs = []
            for j in range(len(PRIMITIVES)):
                if switches_reduce[i][j]:
                    idxs.append(j)
            if sp == len(num_to_keep) - 1:
                drop = get_min_k_no_zero(
                    reduce_prob[i, :], idxs, num_to_drop[sp])
            else:
                drop = get_min_k(reduce_prob[i, :], num_to_drop[sp])
            for idx in drop:
                switches_reduce[i][idxs[idx]] = False
        logging.info('switches_normal = %s', switches_normal)
        logging_switches(switches_normal)
        logging.info('switches_reduce = %s', switches_reduce)
        logging_switches(switches_reduce)

        if sp == len(num_to_keep) - 1:
            arch_param = model.module.arch_parameters()
            normal_prob = F.softmax(
                arch_param[0], dim=sm_dim).data.cpu().numpy()
            reduce_prob = F.softmax(
                arch_param[1], dim=sm_dim).data.cpu().numpy()
            normal_final = [0 for idx in range(14)]
            reduce_final = [0 for idx in range(14)]
            # remove all Zero operations
            for i in range(14):
                if switches_normal_2[i][0] == True:
                    normal_prob[i][0] = 0
                normal_final[i] = max(normal_prob[i])
                if switches_reduce_2[i][0] == True:
                    reduce_prob[i][0] = 0
                reduce_final[i] = max(reduce_prob[i])
            # Generate Architecture, similar to DARTS
            keep_normal = [0, 1]
            keep_reduce = [0, 1]
            n = 3
            start = 2
            for i in range(3):
                end = start + n
                tbsn = normal_final[start:end]
                tbsr = reduce_final[start:end]
                edge_n = sorted(range(n), key=lambda x: tbsn[x])
                keep_normal.append(edge_n[-1] + start)
                keep_normal.append(edge_n[-2] + start)
                edge_r = sorted(range(n), key=lambda x: tbsr[x])
                keep_reduce.append(edge_r[-1] + start)
                keep_reduce.append(edge_r[-2] + start)
                start = end
                n = n + 1
            # set switches according the ranking of arch parameters
            for i in range(14):
                if not i in keep_normal:
                    for j in range(len(PRIMITIVES)):
                        switches_normal[i][j] = False
                if not i in keep_reduce:
                    for j in range(len(PRIMITIVES)):
                        switches_reduce[i][j] = False
            # translate switches into genotype
            genotype = parse_network(switches_normal, switches_reduce)
            logging.info(genotype)
            # restrict skipconnect (normal cell only)
            logging.info('Restricting skipconnect...')
            # generating genotypes with different numbers of skip-connect operations
            for sks in range(0, 9):
                max_sk = 8 - sks
                num_sk = check_sk_number(switches_normal)
                if not num_sk > max_sk:
                    continue
                while num_sk > max_sk:
                    normal_prob = delete_min_sk_prob(
                        switches_normal, switches_normal_2, normal_prob)
                    switches_normal = keep_1_on(switches_normal_2, normal_prob)
                    switches_normal = keep_2_branches(
                        switches_normal, normal_prob)
                    num_sk = check_sk_number(switches_normal)
                logging.info('Number of skip-connect: %d', max_sk)
                genotype = parse_network(switches_normal, switches_reduce)
                logging.info(genotype)


def train(train_queue,
          valid_queue,
          external_queue,
          model,
          model_w,
          model_h,
          model_v,
          network_params,
          criterion,
          optimizer,
          optimizer_a,
          optimizer_w,
          optimizer_h,
          optimizer_v,
          lr,
          lr_w,
          lr_h,
          train_arch=True):
    objs = utils.AvgrageMeter()
    top1 = utils.AvgrageMeter()
    top5 = utils.AvgrageMeter()

    for step, (input, target) in enumerate(train_queue):
        model.train()
        n = input.size(0)
        input = input.to("cuda", dtype=torch.float)
        target = target.to("cuda", dtype=torch.long)

    # for step, data in enumerate(train_queue):
    #     input = data['image']
    #     target = data['label']
    #     input = input v
    #     target = target.to("cuda", dtype=torch.long)
    #     model.train()
    #     n = input.size(0) 

        # external data.
        try:
            input_external, target_external = next(external_queue_iter)
            # data_external = next(external_queue_iter)
        except:
            external_queue_iter = iter(external_queue)
            input_external, target_external = next(external_queue_iter)
            # data_external = next(external_queue_iter)

        input_external = input_external.to("cuda", dtype=torch.float)
        target_external = target_external.to("cuda", dtype=torch.long)
        # input_external = data_external['image'].to("cuda", dtype=torch.float)
        # target_external = data_external['label'].to("cuda", dtype=torch.long) 

        if train_arch:
            # In the original implementation of DARTS, it is input_search, target_search = next(iter(valid_queue), which slows down
            # the training when using PyTorch 0.4 and above.
            try:
                input_search, target_search = next(valid_queue_iter)
                # data_search = next(valid_queue_iter)
            except:
                valid_queue_iter = iter(valid_queue)
                input_search, target_search = next(valid_queue_iter)
                # data_search = next(valid_queue_iter)
            
            input_search = input_search.to("cuda", dtype=torch.float)
            target_search = target_search.to("cuda", dtype=torch.long)
            # input_search = data_search['image'].to("cuda", dtype=torch.float)
            # target_search = data_search['label'].to("cuda", dtype=torch.long) 

            optimizer_a.zero_grad()
            # logits = model(input_search)
            # loss_a = criterion(logits, target_search)
            # loss_a.backward()
            logits_external = model(input_external)
            loss_a = F.cross_entropy(
                logits_external, target_external, reduction='none')
            binary_scores_external = model_v(model_w(input_external))
            binary_weight_external = F.softmax(binary_scores_external, 1)
            loss_a = binary_weight_external[:, 1] * loss_a
            loss_a = loss_a.mean()
            loss_a.backward()
            nn.utils.clip_grad_norm_(
                model.module.arch_parameters(), args.grad_clip)
            optimizer_a.step()

            optimizer_v.zero_grad()
            teacher_logits = model_h(model_w(input_search))
            left_loss = args.weight_lambda * criterion(
                teacher_logits, target_search)

            model_logits_external = model(input_external)
            right_loss = F.cross_entropy(
                model_logits_external, target_external, reduction='none')
            binary_scores_external = model_v(model_w(input_external))
            binary_weight_external = F.softmax(binary_scores_external, 1)
            right_loss = - binary_weight_external[:, 1] * right_loss
            loss_v = left_loss + right_loss.mean()
            loss_v.backward()
            nn.utils.clip_grad_norm_(
                model_v.parameters(), args.grad_clip)
            optimizer_v.step()


        optimizer.zero_grad()
        logits = model(input)
        loss = criterion(logits, target)

        loss.backward()
        nn.utils.clip_grad_norm_(network_params, args.grad_clip)
        optimizer.step()

        # update the parameter of w and h in teacher.
        optimizer_w.zero_grad()
        optimizer_h.zero_grad()

        teacher_logits = model_h(model_w(input))
        # left_loss = criterion(teacher_logits, target)
        left_loss = criterion(teacher_logits + 1e-12, target)

        teacher_features = model_w(input_external)
        teacher_logits_external = model_h(teacher_features)
        right_loss = F.cross_entropy(
            teacher_logits_external, target_external, reduction='none')
        binary_scores_external = model_v(teacher_features)
        binary_weight_external = F.softmax(binary_scores_external, 1)
        right_loss = args.weight_gamma * \
            binary_weight_external[:, 1] * right_loss
        loss = left_loss + right_loss.mean()
        loss.backward()
        nn.utils.clip_grad_norm_(model_w.parameters(), args.grad_clip)
        nn.utils.clip_grad_norm_(model_h.parameters(), args.grad_clip)

        optimizer_w.step()
        optimizer_h.step()

        prec1, prec5 = utils.accuracy(logits, target, topk=(1, 5))
        # prec1, prec5 = utils.accuracy(logits, target, topk=(1, 2))
        objs.update(loss.data.item(), n)
        top1.update(prec1.data.item(), n)
        top5.update(prec5.data.item(), n)

        if step % args.report_freq == 0:
            logging.info('TRAIN Step: %03d Objs: %e R1: %f R5: %f',
                         step, objs.avg, top1.avg, top5.avg)

    return top1.avg, objs.avg


def infer(valid_queue, model, criterion):
    objs = utils.AvgrageMeter()
    top1 = utils.AvgrageMeter()
    top5 = utils.AvgrageMeter()
    model.eval()

    with torch.no_grad():
        for step, (input, target) in enumerate(valid_queue):
            input = input.to("cuda", dtype=torch.float)
            target = target.to("cuda", dtype=torch.long)
        # for step, data in enumerate(valid_queue):
        #     input = data['image']
        #     target = data['label']
        #     input = input.to("cuda", dtype=torch.float)
        #     target = target.to("cuda", dtype=torch.long) 

            with torch.no_grad():
                logits = model(input)
                # loss = criterion(logits, target)
                loss = criterion(logits + 1e-12, target)

            prec1, prec5 = utils.accuracy(logits, target, topk=(1, 5))
            # prec1, prec5 = utils.accuracy(logits, target, topk=(1, 2))
            n = input.size(0)
            objs.update(loss.data.item(), n)
            top1.update(prec1.data.item(), n)
            top5.update(prec5.data.item(), n)

            if step % args.report_freq == 0:
                logging.info('valid %03d %e %f %f', step,
                             objs.avg, top1.avg, top5.avg)

    return top1.avg, objs.avg


def parse_network(switches_normal, switches_reduce):

    def _parse_switches(switches):
        n = 2
        start = 0
        gene = []
        step = 4
        for i in range(step):
            end = start + n
            for j in range(start, end):
                for k in range(len(switches[j])):
                    if switches[j][k]:
                        gene.append((PRIMITIVES[k], j - start))
            start = end
            n = n + 1
        return gene
    gene_normal = _parse_switches(switches_normal)
    gene_reduce = _parse_switches(switches_reduce)

    concat = range(2, 6)

    genotype = Genotype(
        normal=gene_normal, normal_concat=concat,
        reduce=gene_reduce, reduce_concat=concat
    )

    return genotype


def get_min_k(input_in, k):
    input = copy.deepcopy(input_in)
    index = []
    for i in range(k):
        idx = np.argmin(input)
        index.append(idx)
        input[idx] = 1

    return index


def get_min_k_no_zero(w_in, idxs, k):
    w = copy.deepcopy(w_in)
    index = []
    if 0 in idxs:
        zf = True
    else:
        zf = False
    if zf:
        w = w[1:]
        index.append(0)
        k = k - 1
    for i in range(k):
        idx = np.argmin(w)
        w[idx] = 1
        if zf:
            idx = idx + 1
        index.append(idx)
    return index


def logging_switches(switches):
    for i in range(len(switches)):
        ops = []
        for j in range(len(switches[i])):
            if switches[i][j]:
                ops.append(PRIMITIVES[j])
        logging.info(ops)


def check_sk_number(switches):
    count = 0
    for i in range(len(switches)):
        if switches[i][3]:
            count = count + 1

    return count


def delete_min_sk_prob(switches_in, switches_bk, probs_in):
    def _get_sk_idx(switches_in, switches_bk, k):
        if not switches_in[k][3]:
            idx = -1
        else:
            idx = 0
            for i in range(3):
                if switches_bk[k][i]:
                    idx = idx + 1
        return idx
    probs_out = copy.deepcopy(probs_in)
    sk_prob = [1.0 for i in range(len(switches_bk))]
    for i in range(len(switches_in)):
        idx = _get_sk_idx(switches_in, switches_bk, i)
        if not idx == -1:
            sk_prob[i] = probs_out[i][idx]
    d_idx = np.argmin(sk_prob)
    idx = _get_sk_idx(switches_in, switches_bk, d_idx)
    probs_out[d_idx][idx] = 0.0

    return probs_out


def keep_1_on(switches_in, probs):
    switches = copy.deepcopy(switches_in)
    for i in range(len(switches)):
        idxs = []
        for j in range(len(PRIMITIVES)):
            if switches[i][j]:
                idxs.append(j)
        drop = get_min_k_no_zero(probs[i, :], idxs, 2)
        for idx in drop:
            switches[i][idxs[idx]] = False
    return switches


def keep_2_branches(switches_in, probs):
    switches = copy.deepcopy(switches_in)
    final_prob = [0.0 for i in range(len(switches))]
    for i in range(len(switches)):
        final_prob[i] = max(probs[i])
    keep = [0, 1]
    n = 3
    start = 2
    for i in range(3):
        end = start + n
        tb = final_prob[start:end]
        edge = sorted(range(n), key=lambda x: tb[x])
        keep.append(edge[-1] + start)
        keep.append(edge[-2] + start)
        start = end
        n = n + 1
    for i in range(len(switches)):
        if not i in keep:
            for j in range(len(PRIMITIVES)):
                switches[i][j] = False
    return switches


if __name__ == '__main__':
    start_time = time.time()
    main()
    end_time = time.time()
    duration = end_time - start_time
    logging.info('Total searching time: %ds', duration)
