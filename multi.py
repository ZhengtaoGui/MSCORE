from numpy import linalg as LA
from scipy.sparse.linalg.eigen.arpack import eigsh as largest_eigsh
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics.cluster import adjusted_rand_score
from scipy.optimize import Bounds
from scipy.optimize import LinearConstraint
from scipy.sparse.linalg import eigs
from sklearn.cluster import SpectralClustering
from scipy.optimize import minimize
import numpy as np
import commFunc
import random
import math
import networkx as nx


def projection_simplex_sort(v, z=1):
    n_features = v.shape[0]
    u = np.sort(v)[::-1]
    cssv = np.cumsum(u) - z
    ind = np.arange(n_features) + 1
    cond = u - cssv / ind > 0
    rho = ind[cond][-1]
    theta = cssv[cond][-1] / float(rho)
    w = np.maximum(v - theta, 0)
    return w

def EDC(w,Ares,k):
    wadj = np.tensordot(w,Ares,axes=1);
    v,u = largest_eigsh(wadj,k+1,which='LM');
    v_abs = abs(v);
    u = np.real(u[:,v_abs.argsort()]);
    v = v[v_abs.argsort()];
    return v,u

def EDCS(w,Ares,k):
    wadj = np.tensordot(w,Ares,axes=1);
    label = SCORE(wadj,k,30,'gmm')
    return label

def tau_cal(n,rho,k,in_list,out_list):
    L = len(in_list)
    res = 0
    for i in range(L):
        p = rho*in_list[i]
        q = rho*out_list[i]
        b = p-q
        c = p*(1-p)+(k-1)*q*(1-q)
        res+=b**2/c

    return res*n


def ratio(v):
    return -(v[1]/v[0])**2

def ratio_der(v,u,Ares):
    der_1 = np.tensordot(np.tensordot(Ares,u[:,1],axes=1),u[:,1],axes=1);
    der_0 = np.tensordot(np.tensordot(Ares,u[:,0],axes=1),u[:,0],axes=1);
    return -2*v[1]*(v[0]*der_1-v[1]*der_0)/v[0]**3

class SCME:
    
    def __init__(self,Alist,k,method='gmm'):
        self.A = Alist
        self.k = k
        self.L = len(Alist)
        self.method = method
    
    def singleUpdate(self,lamb,lr0=0.05,th=1e-4,iteration=10,decay=1,epsilon=1e-3):
        
        t = 0
        while t<iteration:
            
            lr = lr0/(1+decay*t)
            t += 1
            
            ## Calculate eigenvalue
            v, u = EDC(lamb,self.A,self.k)
            grad = ratio_der(v,u,self.A)
            
            if sum(grad**2)**0.5<th:
                break
            
            lamb = lamb-lr*grad;
            lamb = projection_simplex_sort(lamb);
            #print(t,lamb,abs(v[1]/v[0]))
        
        eratio = abs(v[1]/v[0]);
        
        return(lamb,eratio)
    
    def multipleUpdate(self,itr=10,lr0=0.05,th=1e-4,iteration=10,decay=1,epsilon=1e-3):
        
        eratio_res = 0
        label_res = 0
        lamb_res = 0
        
        for i in np.arange(itr):
            ## Random Initialization
            lamb = np.random.uniform(low=0,high=1,size=self.L)
            lamb = projection_simplex_sort(lamb)
            lamb,eratio = self.singleUpdate(lamb,lr0,th,iteration,decay,epsilon)
            if eratio>eratio_res:
                eratio_res,lamb_res = eratio,lamb
        
        return(lamb_res,eratio_res)
    
    def optimize(self,n_init=10,update="multiple",lamb = 0,itr=10,
                 lr0=0.05,th=1e-3,iteration=10,decay=1, epsilon=1e-3):
        
        if self.L==1:
            lamb = np.array([1.0])
        elif update == "multiple":
            lamb,_ = self.multipleUpdate(itr,lr0,th,iteration,decay,epsilon)
        elif update == "single":
            lamb,_ = self.singleUpdate(lamb,lr0,th,iteration,decay,epsilon)
        v, u = EDC(lamb,self.A,self.k)
        eratio = abs(v[1]/v[0])
        
        if self.method == 'gmm':  
            label = GaussianMixture(n_components=self.k,n_init=n_init).fit_predict(u[:,1:])
        else :
            label = KMeans(n_clusters=self.k,n_init=n_init).fit_predict(u[:,1:])
            
        return label,lamb,eratio

    
    

def genDBer(A,n_k,theta,symm=True):
    k = len(n_k)
    res = np.zeros((1,sum(n_k)))
    for i in np.arange(k):
        block = A[i,0]*np.ones((n_k[i],n_k[0]))
        for j in np.arange(1,k):
            block = np.concatenate((block, A[i,j]*np.ones((n_k[i],n_k[j]))), axis=1)
        res = np.concatenate((res,block),axis=0)
    res = res[1:,:]
    for i in np.arange(sum(n_k)):
        for j in np.arange(sum(n_k)):
            res[i,j] = res[i,j]*theta[i]*theta[j]
            if(res[i,j]>1):
                res[i,j] = 1
    
    if symm:
        gen = np.tril(res,-1)
        gen = np.random.binomial(1,gen)
        gen = gen+gen.T
    else:
        gen = np.random.binomial(1,res)
    
    return res,gen




def genBer(A,n_k,symm=True):
    k = len(n_k)
    res = np.zeros((1,sum(n_k)))
    for i in np.arange(k):
        block = A[i,0]*np.ones((n_k[i],n_k[0]))
        for j in np.arange(1,k):
            block = np.concatenate((block, A[i,j]*np.ones((n_k[i],n_k[j]))), axis=1)
        res = np.concatenate((res,block),axis=0)
    res = res[1:,:]
    
    if symm:
        gen = np.tril(res,-1)
        gen = np.random.binomial(1,gen)
        gen = gen+gen.T
    else:
        gen = np.random.binomial(1,res)
        
    
    return res,gen


# DSC算法
class DSC:
    
    def __init__(self,Alist,k,method='gmm'):
        self.Alist = Alist
        self.k = k
        self.n = Alist[0].shape[0]
        self.L = len(Alist)
        self.method = method
        # 定义网络参数，与聚类方法
    
    def weight_single(self,A,label):
        cnt_in = 0
        sum_in = 0
        for i in range(self.k):
            idx = np.where(label==i)[0]
            sum_in += np.sum(A[idx, :][:, idx])
            cnt_in += len(idx)**2
        sum_out = np.sum(A) - sum_in
        cnt_out = self.n**2-cnt_in
        return (sum_in/cnt_in-sum_out/cnt_out)/(sum_in/cnt_in+(self.k-1)*sum_out/cnt_out)
    
    def weight_multi(self,init = False,label=[],n_init=10):
        w = np.empty(self.L)
        
        for i in range(len(self.Alist)):
            if init:
                label = SCORE(self.Alist[i].astype(float),self.k,30,self.method)
    
            w[i] = self.weight_single(self.Alist[i],label)
        
        w = np.maximum(w,np.zeros(self.L))
        if np.sum(w)==0:
            w = np.random.randint(low=1,high=10,size=self.L)
        return w/np.sum(w)

    def wam(self,w,n_init=10):
        return SCORE(np.tensordot(w,self.Alist,axes=1),self.k,30,self.method)
    
    def opt(self,eps=1e-3,max_it=100,n_init=10):
        
        w_old = self.weight_multi(init=True)
        
        it = 0
        while it<max_it:
            it +=1
            label = self.wam(w_old)
            w_new = self.weight_multi(label=label,init=False,n_init=n_init)
            if sum((w_new-w_old)**2)<eps:
                break
            w_old = w_new
        
        return w_new,self.wam(w_new)

    
def obtain_U(A,KC):
    N = A.shape[0]
    tr = np.zeros((N, N, N))
    for i in range(N):
        for j in range(N):
            for l in range(N):
                tr[i,j,l] = A[i,j]*A[i,l]*A[j,l]
    sc = SpectralClustering(n_clusters=KC, affinity='precomputed')
    g = sc.fit_predict(A)
    S = np.zeros((N, N))
    for i in range(KC):
        Sk = np.zeros((N, N))
        for m in range(N):
            if g[m] == i:
                Sk = Sk + tr[:,:,m]
        S = S + Sk.T.dot(Sk)
    sc1 = SpectralClustering(n_clusters=KC, affinity='precomputed')
    label = sc1.fit_predict(S)
    return label


# ISC算法
class SumSVD:
    
    def __init__(self,Alist,k,method='gmm'):
        self.Alist = Alist
        self.k = k
        self.n = Alist[0].shape[0]
        self.L = len(Alist)
        self.method = method
        # 定义网络参数，与聚类方法
    
    def weight_single(self,A,label):
        cnt_in = 0
        sum_in = 0
        for i in range(self.k):
            idx = np.where(label==i)[0]
            sum_in += np.sum(A[idx, :][:, idx])
            cnt_in += len(idx)**2
        sum_out = np.sum(A) - sum_in
        cnt_out = self.n**2-cnt_in
        return (sum_in/cnt_in-sum_out/cnt_out)/(sum_in/cnt_in+(self.k-1)*sum_out/cnt_out)
    
    def weight_multi(self,init = False,label=[],n_init=10):
        w = np.empty(self.L)
        
        for i in range(len(self.Alist)):
            if init:
                label = obtain_U(self.Alist[i].astype(float), self.k)
    
            w[i] = self.weight_single(self.Alist[i],label)
        
        w = np.maximum(w,np.zeros(self.L))
        if np.sum(w)==0:
            w = np.random.randint(low=1,high=10,size=self.L)
        return w/np.sum(w)

    def wam(self,w,n_init=10):
        return obtain_U(np.tensordot(w,self.Alist,axes=1),self.k)
    
    def opt(self,eps=1e-3,max_it=100,n_init=10):
        
        w_old = self.weight_multi(init=True)
        it = 0
        while it<max_it:
            it +=1
            label = self.wam(w_old)
            w_new = self.weight_multi(label=label,init=False,n_init=n_init)
            if sum((w_new-w_old)**2)<eps:
                break
            w_old = w_new
        
        return w_new,self.wam(w_new)

# ISC算法
class ISC:
    
    def __init__(self,Alist,k,method='gmm'):
        self.Alist = Alist
        self.k = k
        self.n = Alist[0].shape[0]
        self.L = len(Alist)
        self.method = method
        # 定义网络参数，与聚类方法
    
    def weight_single(self,A,label):
        cnt_in = 0
        sum_in = 0
        for i in range(self.k):
            idx = np.where(label==i)[0]
            sum_in += np.sum(A[idx, :][:, idx])
            cnt_in += len(idx)**2
        sum_out = np.sum(A) - sum_in
        cnt_out = self.n**2-cnt_in
        return (sum_in/cnt_in-sum_out/cnt_out)/(sum_in/cnt_in+(self.k-1)*sum_out/cnt_out)
    
    def weight_multi(self,init = False,label=[],n_init=10):
        w = np.empty(self.L)
        
        for i in range(len(self.Alist)):
            if init:
                sc = SpectralClustering(n_clusters=self.k, affinity='precomputed')
                label = sc.fit_predict(self.Alist[i].astype(float))
    
            w[i] = self.weight_single(self.Alist[i],label)
        
        w = np.maximum(w,np.zeros(self.L))
        if np.sum(w)==0:
            w = np.random.randint(low=1,high=10,size=self.L)
        return w/np.sum(w)

    def wam(self,w,n_init=10):
        sc1 = SpectralClustering(n_clusters=self.k, affinity='precomputed')
        labe = sc1.fit_predict(np.tensordot(w,self.Alist,axes=1))
        return labe
    
    def opt(self,eps=1e-3,max_it=100,n_init=10):
        
        w_old = self.weight_multi(init=True)
        it = 0
        while it<max_it:
            it +=1
            label = self.wam(w_old)
            w_new = self.weight_multi(label=label,init=False,n_init=n_init)
            if sum((w_new-w_old)**2)<eps:
                break
            w_old = w_new
        
        return w_new,self.wam(w_new)
    
class MAM:
    def __init__(self,Alist,asso,k):
        self.Alist=Alist
        self.k = k
        self.n = Alist[0].shape[0]
        self.asso=asso
    
    def _Nam(self,comm):
        res = np.zeros((len(comm),len(comm)))
        for i in np.arange(len(comm)):
            for j in np.arange(i+1,len(comm)):
                if comm[i]==comm[j]:
                    res[i][j] = 1
        res = res+res.T
        np.fill_diagonal(res,1)
        return res
    
    def Mam(self,numini=5):
        NGM = []
        res = np.zeros((self.n,self.n))
        for index in np.arange(len(self.Alist)):
            ngm = float("inf")
            if self.asso[index]:
                ngm = -ngm
            for i in np.arange(numini):
                init = np.random.randint(low=0,high=self.k,size=self.n)
                comm,ngm_new = self._tabu_search(init,self.Alist[index],self.k,int(self.n/4), self.asso[index])
                if (self.asso[index] and ngm_new > ngm) or (not self.asso[index] and ngm_new < ngm):
                    ngm = ngm_new
                    comm_best = comm
            NGM.append(comm_best)
        for mod in NGM:
            res += self._Nam(mod)
        return (NGM,res)
    
    def _updateO(self,oldO,oldcommunity,indice,newlabel,Ab):
        oldlabel = oldcommunity[indice]
        newO = np.copy(oldO)
        newcommunity = np.copy(oldcommunity)
        newcommunity[indice] = newlabel
        posi=commFunc.position(newcommunity)
        changeO = sum(Ab[indice,posi[oldlabel]])
        changeN = sum(Ab[indice,posi[newlabel]])
        for j in np.arange(newcommunity.max()+1):
            change = sum(Ab[indice,posi[j]])
            newO[newlabel,j] = newO[newlabel,j]+change+change*(newlabel==j)-changeN*(oldlabel==j)
            newO[oldlabel,j] = newO[oldlabel,j]-change-change*(oldlabel==j)+changeO*(newlabel==j)
        newO[:,newlabel] = np.transpose(newO[newlabel,:])
        newO[:,oldlabel] = np.transpose(newO[oldlabel,:])
        return newO
    
    def _tabu_search(self,ini_community, Ab, k, tabu_size, asso=True, max_iterations=5000, max_stay=200, children=2):
        
        community = np.copy(ini_community)
        old_O = commFunc.O(community,Ab)
        ngm = sum(np.diagonal(old_O))-sum(sum(old_O)**2/np.sum(old_O))
        
        tabu_set = []
        iteration = 0
        stay = 0
        n = Ab.shape[0]
        
        while (iteration < max_iterations) and (stay < max_stay):  #  Stopping Criteria
            
            index =  random.randint(0,n-1) # Generate one randomly
            while index in tabu_set:
                index =  random.randint(0,n-1) # Generate another
            tabu_set = [index] + tabu_set[:tabu_size-1]
            stay = stay+1
            for label in np.setdiff1d(random.sample(range(0, self.k), children),community[index]):
                new_O = self._updateO(old_O,community,index,label,Ab)
                new_ngm = sum(np.diagonal(new_O))-sum(sum(new_O)**2/np.sum(new_O))
                
                if (asso and new_ngm > ngm) or (not asso and new_ngm < ngm):
                    stay = 0
                    old_O=new_O
                    community[index] = label
                    ngm = new_ngm
    
            iteration = iteration + 1
        return(community,ngm)


def ASC(Alist,k):
    res = np.zeros((Alist[0].shape[0],Alist[0].shape[0]))
    for Ab in Alist:
        if min(sum(Ab))+np.sum(Ab)/Ab.shape[0]>0:
            D = np.diag(np.squeeze(np.asarray(1/np.sqrt(sum(Ab)+np.sum(Ab)/Ab.shape[0]))))
        else:
            sigma = 1
            D = np.diag(np.squeeze(np.asarray(1/np.sqrt(sum(Ab)-min(sum(Ab))+sigma))))
        w, v = np.linalg.eig(np.matrix(D)*np.matrix(Ab)*np.matrix(D))
        w = np.array(list(map(abs,w)))
        X = v[:,w.argsort()[-k:][::-1]]
        X = X.real
        res += np.matmul(X,X.T)
    res = res/len(Alist)
    w, v = np.linalg.eig(res)
    w = np.array(list(map(abs,w)))
    X = v[:,w.argsort()[-k:][::-1]]
    kmeans = KMeans(n_clusters=k).fit(np.real(X))
    return(kmeans)




def lam_norm(in_list,out_list,k=2):
    w = [(x-y)/(x+(k-1)*y) for x,y in zip(in_list,out_list)]
    return([x/sum([abs(x) for x in w]) for x in w])



def cond_num(in_list,out_list,k,n,rho):
    return sum([(x-y)/(x+(k-1)*y) for x,y in zip(in_list,out_list)])*n*rho/k



# 产生多层DCBM模型
def genDCBM(n,k,L,rho,pi,Alist,theta):
    n_k = np.random.multinomial(n, pi, size=1)[0] # 多项分布，扔n次骰子，每次的概率为pi
    gt = [n_k[i]*[i] for i in range(k)]
    gt = [elem for vec in gt for elem in vec]    
    Ares = np.zeros((L,n,n)) #生成多层网络的0数组
    for l in range(L):
        A = Alist[l]*rho
        A_mean,A = genDBer(A,n_k,theta)
        Ares[l] = A
    
    return Ares,gt



# 产生多层SBM模型
def genSBM(n,k,L,rho,pi,Alist):
    n_k = np.random.multinomial(n, pi, size=1)[0] # 多项分布，扔n次骰子，每次的概率为pi
    gt = [n_k[i]*[i] for i in range(k)]
    gt = [elem for vec in gt for elem in vec]
    
    Ares = np.zeros((L,n,n)) #生成多层网络的0数组
    for l in range(L):
        A = Alist[l]*rho
        A_mean,A = genBer(A,n_k)
        Ares[l] = A
    
    return Ares,gt



# SCORE算法
def SCORE(matrix,k,n_init,method):
    n_init = 30
    n = len(matrix[0])
    ratio = [[1.]]*n
    lamda = np.linalg.eig(matrix)
    a = sorted(lamda[0], key=abs)
    for i in range(k-1):
        ratio1 = (lamda[1][0:n,np.where(lamda[0]==a[n-2-i])].reshape(1,n))/(lamda[1][0:n,np.where(lamda[0]==a[n-1])].reshape(1,n))
        ratio1 = ratio1.reshape(n,1)
        for j in range(n):
            if(ratio1[j,0]>np.log(n)):
                ratio1[j,0] = np.log(n)
            if(ratio1[j,0]<-np.log(n)):
                ratio1[j,0] = -np.log(n)
            if(np.isnan(ratio1[j,0])):
                ratio1[j,0] = 0.0
        ratio = np.concatenate((ratio,ratio1),axis=1)
    ratio = ratio[:,1:]
    ratio = np.real(ratio)
    #print(ratio)
    if method =='gmm':
        label = GaussianMixture(n_components=k,n_init=n_init).fit_predict(ratio)
    else:
        label = KMeans(n_clusters=k,n_init=n_init).fit_predict(ratio)
    return label


# 谱聚类
def SC(matrix,k,method = 'km',n_init = 30):
    evals, evecs = largest_eigsh(matrix,k,which='LM')
    evals_abs = abs(evals)
    evecs = evecs[:,evals_abs.argsort()]
    evals = evals[evals_abs.argsort()]
    if method =='gmm':
        label = GaussianMixture(n_components=k,n_init=n_init).fit_predict(np.real(evecs[:,:]))
    else:
        label = KMeans(n_clusters=k,n_init=n_init).fit_predict(np.real(evecs[:,:]))
    return label
