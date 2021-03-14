import pandas as pd
import numpy as np
import pickle
import matplotlib.pyplot as plt
import spacy 
from gensim.models import FastText
from gensim.models import KeyedVectors
from sklearn import metrics
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.model_selection import GridSearchCV
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import matthews_corrcoef
from sklearn import svm

class support_vector_machine:
    
    def __init__(self, mutated_dst):
        
        self.mutated = mutated_dst[['task_complete','consistent']]
        
        self.X = self.mutated['task_complete']
        self.y = self.mutated['consistent']
        
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(self.X, self.y, test_size=0.2, random_state=42)
        
    def fasttextskip(self):
        
        tasks_train_w2v = [row for row in self.X_train]
        vector_size = 100
        w2v_model_tasks = FastText(tasks_train_w2v, sg = 1, size = vector_size, window=6, min_count=1, workers=4, iter= 1000)
        
        return w2v_model_tasks, vector_size
    
    @staticmethod
    def make_feature_vec(words, model, emb_size):
        """
        Average the word vectors for a set of words
        """
        feature_vec = np.zeros((emb_size,),dtype="float32")  # pre-initialize (for speed)
        nwords = 0.
        index2word_set = set(model.wv.index2word)  # words known to the model

        for word in words:
            if word in index2word_set: 
                nwords = nwords + 1.
                feature_vec = np.add(feature_vec,model[word])

        nwords = np.array([nwords])

        feature_vec = feature_vec / nwords[:,None]
        return feature_vec    
    
    def get_avg_feature_vecs(self,tasks, model, emb_size):
        """
        Calculate average feature vectors for all tasks
        """
        counter = 0
        tasks_feature_vecs = np.zeros((len(tasks),emb_size), dtype='float64')  # pre-initialize (for speed)

        for task in tasks:
            tasks_feature_vecs[counter] = self.make_feature_vec(task, model, emb_size)
            counter = counter + 1
        return tasks_feature_vecs
    
    def prepare_train_test_tasks(self, model_tasks, emb_size):
        
        clean_train_tasks = [task for task in self.X_train]

        trainDataVecs = self.get_avg_feature_vecs(clean_train_tasks, model_tasks, emb_size)        
        
        clean_test_tasks = [task for task in self.X_test]

        testDataVecs = self.get_avg_feature_vecs(clean_test_tasks, model_tasks, emb_size)
        
        return trainDataVecs,testDataVecs    
    
    def run_svm(self):
        
        fasttext, emb_size = self.fasttextskip()
        
        train_data_vecs, test_data_vecs = self.prepare_train_test_tasks(fasttext, emb_size)
        
        param_grid = {'C': [0.1, 1, 10, 100, 1000],  
              'gamma': [1, 0.1, 0.01, 0.001, 0.0001]}       
        
        svm_clf = svm.SVC(kernel='rbf',probability=True)
        
        cv = StratifiedKFold(n_splits=10,
                     shuffle=True,
                     random_state=42)
        
        grid_search = GridSearchCV(estimator = svm_clf, param_grid = param_grid, 
                          cv = cv, n_jobs = -1, verbose = 2)
        
        svm_hyper = grid_search.fit(train_data_vecs, self.y_train)
        
        best_grid = grid_search.best_estimator_
        
        result = best_grid.predict(test_data_vecs)
        
        class_report = classification_report(self.y_test, result, output_dict = True)
        
        probs = best_grid.predict_proba(test_data_vecs)[:, 1]

        fpr, tpr, _ = roc_curve(self.y_test, probs)
        auc = roc_auc_score(self.y_test, probs)
        
        mat = matthews_corrcoef(self.y_test, result)
        
        return class_report, best_grid, fpr, tpr, auc, mat
        
        
def get_filtered_mutated(mt,mod):
    
    mt = mt[mt['mod_keys_found_string'] == mod]
    
    return mt

def results_to_dict(results):
    
    end_dict = {}
    end_dict['acc'] = round(results['accuracy'],3)
    neg_keys = ['precision_neg_cl', 'recall_neg_cl', 'f1_score_neg']

    mod = 'shell'
    norm = results['0']
    neg = results['1']
    del neg['support']
    del norm['support']

    for key in norm.keys():
        norm[key] = round(norm[key],3)
        neg[key] = round(neg[key],3)

    for key,n_key in zip(list(neg.keys()), neg_keys):
        neg[n_key] = neg.pop(key)
    z = {**norm, **neg}
    end_dict = {**end_dict, **z}
    
    return end_dict

if __name__ == "__main__":
    
    with open('mutated.pkl', 'rb') as input_file:
        mutated = pickle.load(input_file)
        
    with open('top10_list.pkl', 'rb') as input_file:
        top10_list = pickle.load(input_file)
        
    mutated['consistent'] = mutated['consistent'].astype(int)
    
    metrics = ['acc',
          'precision',
          'recall',
          'f1-score',
          'precision_neg_cl',
          'recall_neg_cl',
          'f1_score_neg',
          'matthews',
          'roc_auc']
        
    results_df = pd.DataFrame(index = metrics)
    
    for module in top10_list:
        
        print('Running SVM for the module ', module)
        
        filtered_mutated = get_filtered_mutated(mutated, module)
    
        svm_obj = support_vector_machine(filtered_mutated)

        report_dict, best_params, fpr, tpr, auc, mat = svm_obj.run_svm()
        
        print('The best estimators for the module ', module, ' are: ', best_params)
        
        file_title = 'skip/svm_best_params/svm_fasttext_best_params_' + module + '.pkl'
        with open(file_title,'wb') as output_file:
            pickle.dump(best_params, output_file)
        
        column_dict = results_to_dict(report_dict)
        
        column_dict['matthews'] = round(mat,3)
        column_dict['roc_auc'] = round(auc,3)
        
        results_df[module] = results_df.index.to_series().map(column_dict)
        
        plt.figure(1)
        plt.plot([0, 1], [0, 1], 'k--')
        plt.plot(fpr, tpr, label='AUC {:.3f}'.format(auc))
        plt.xlabel('False positive rate')
        plt.ylabel('True positive rate')
        plt.title('ROC curve')
        plt.legend(loc='best')
        path = 'skip/svm/svm_fasttext_'+ module + '.jpg'
        plt.savefig(path)
        plt.clf()
        
        print('For module ', module, ' the results are ', column_dict)
        print('=====================================')
        
    print(results_df)
    results_df.to_excel('skip/svm_fasttext.xlsx')